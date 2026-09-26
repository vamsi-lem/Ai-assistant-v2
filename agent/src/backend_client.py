"""
The agent's only link to the rest of the platform.

The agent holds no database credentials and knows nothing about Supabase. It
is handed a room named `call-<id>`, recovers the id, and asks the backend for
everything else. That keeps the service key in one process instead of two, and
it is why the same agent code serves a browser participant today and a phone
participant later without changing.

All calls are async. A blocking HTTP request inside the agent's event loop
would stall audio, voice detection and turn taking for the length of the round
trip, which on a live call is audible.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .config import config

logger = logging.getLogger("agent.backend")

ROOM_PREFIX = config.room_prefix


def call_id_from_room(room_name: str) -> str | None:
    """
    Recover the call id from the room name.

    Returns None for any room that is not one of ours, so a stray room in the
    same LiveKit project makes the agent leave rather than guess.
    """
    if not room_name or not room_name.startswith(ROOM_PREFIX):
        return None
    call_id = room_name[len(ROOM_PREFIX) :].strip()
    return call_id or None


class BackendClient:
    """One aiohttp session per job, closed on shutdown."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _ensure(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-Agent-Key": config.agent_api_key,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
                # A fresh connection per request. The backend closes idle
                # keep-alive connections after a few seconds, and reusing
                # one that was closed fails with "Server disconnected"
                # (seen on the periodic transcript save). Reconnecting to
                # localhost costs a millisecond; a lost save costs a turn.
                connector=aiohttp.TCPConnector(force_close=True),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # -- reads --------------------------------------------------------------

    async def fetch_call_context(self, call_id: str) -> dict[str, Any]:
        """
        Who are we calling and what about.

        Raises on failure. A call with no context is one the agent should not
        attempt: it would have to invent a name, which is worse than silence.
        """
        session = await self._ensure()
        url = f"{config.backend_base_url}/calls/{call_id}/context"

        async with session.get(url) as response:
            if response.status == 401:
                raise RuntimeError(
                    "Backend rejected the agent key. AGENT_API_KEY in agent/.env "
                    "must match backend/.env exactly."
                )
            if response.status == 404:
                raise RuntimeError(f"Backend has no call with id {call_id}.")
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Backend returned {response.status}: {body[:300]}")
            return await response.json()

    # -- writes -------------------------------------------------------------

    async def store_conversation(
        self,
        *,
        call_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
        call_status: str | None = None,
    ) -> None:
        """
        Persist the transcript.

        Sends the COMPLETE turn list every time. The backend replaces rather
        than appends, so a retried or duplicated flush can never double up a
        turn. That is worth slightly more bytes on the wire.
        """
        session = await self._ensure()
        url = f"{config.backend_base_url}/conversations"

        payload: dict[str, Any] = {"call_id": call_id, "messages": messages}
        if summary is not None:
            payload["summary"] = summary
        if call_status is not None:
            payload["call_status"] = call_status

        async with session.post(url, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                # Deliberately a warning, not a raise. Losing a transcript is
                # bad; killing a live call because a write failed is worse.
                logger.warning(
                    "Could not store transcript for call %s: %s %s",
                    call_id,
                    response.status,
                    body[:300],
                )

    async def book_slot(
        self,
        *,
        lead_id: str,
        call_id: str,
        scheduled_at: str,
        requested_text: str | None = None,
        notes: str | None = None,
        meeting_platform: str | None = None,
    ) -> tuple[bool, str]:
        """
        Book a counsellor slot. The backend saves it, creates the meeting
        link and sends the WhatsApp. Returns (ok, message) where message is
        written for the brain to act on: on success it says how to read the
        time back and whether the link was sent; on a bad time it says what
        to ask the lead. Never raises into the conversation.
        """
        session = await self._ensure()
        url = f"{config.backend_base_url}/bookings"
        payload: dict[str, Any] = {
            "lead_id": lead_id,
            "call_id": call_id,
            "scheduled_at": scheduled_at,
        }
        if requested_text:
            payload["requested_text"] = requested_text
        if notes:
            payload["notes"] = notes
        if meeting_platform:
            payload["meeting_platform"] = meeting_platform

        fallback = (
            "The booking could not be saved right now. Tell the lead a counsellor "
            "will call to confirm the time."
        )
        try:
            async with session.post(url, json=payload) as response:
                body = await response.json(content_type=None)
                if response.status == 422:
                    detail = body.get("detail") if isinstance(body, dict) else None
                    if isinstance(detail, list):  # pydantic validation shape
                        detail = "; ".join(str(d.get("msg", d)) for d in detail)
                    return False, str(detail or "That time could not be understood. Ask the lead again.")
                if response.status >= 400:
                    logger.warning("Booking failed for lead %s: %s %s", lead_id, response.status, str(body)[:300])
                    return False, fallback
                return True, f"Booked for {body['spoken_time']}. {body['link_status']}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Booking failed for lead %s: %s", lead_id, exc)
            return False, fallback

    async def save_callback(
        self,
        *,
        lead_id: str,
        callback_time: str | None = None,
        callback_notes: str | None = None,
    ) -> bool:
        """
        Record when a counsellor should ring back, and anything the lead
        asked that Maya could not answer. Written the moment it is known,
        not at the end of the call, so a dropped line does not lose it.
        Returns True on success; never raises into the conversation.
        """
        session = await self._ensure()
        url = f"{config.backend_base_url}/leads/{lead_id}/callback"

        payload: dict[str, Any] = {}
        if callback_time is not None:
            payload["callback_time"] = callback_time
        if callback_notes is not None:
            payload["callback_notes"] = callback_notes

        try:
            async with session.patch(url, json=payload) as response:
                if response.status >= 400:
                    body = await response.text()
                    logger.warning(
                        "Could not save callback for lead %s: %s %s",
                        lead_id,
                        response.status,
                        body[:300],
                    )
                    return False
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save callback for lead %s: %s", lead_id, exc)
            return False
