"""
Zoom, through a Server-to-Server OAuth app.

Three values from marketplace.zoom.us (Develop -> Build App -> Server-to-
Server OAuth): Account ID, Client ID, Client Secret. The app needs the
`meeting:write:admin` scope (on newer Zoom accounts it is called
`meeting:write:meeting:admin`; either works). No user ever logs in; the
backend exchanges the three values for a short-lived access token and
creates the meeting under the host user (`ZOOM_HOST_USER`, default "me",
meaning the account owner).

A free Zoom account is enough: the meeting exists, the link works, and the
40 minute cap on free accounts is longer than a counselling call.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime

import httpx

from ...config import get_settings
from .base import MeetingError, MeetingLink, MeetingNotConfigured

logger = logging.getLogger("backend.meetings.zoom")

TOKEN_URL = "https://zoom.us/oauth/token"
API_BASE = "https://api.zoom.us/v2"


class ZoomProvider:
    name = "zoom"

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.zoom_account_id and s.zoom_client_id and s.zoom_client_secret)

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        # Tokens last an hour; reuse until a minute before expiry.
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token

        s = get_settings()
        basic = base64.b64encode(f"{s.zoom_client_id}:{s.zoom_client_secret}".encode()).decode()
        response = await client.post(
            TOKEN_URL,
            params={"grant_type": "account_credentials", "account_id": s.zoom_account_id},
            headers={"Authorization": f"Basic {basic}"},
        )
        if response.status_code != 200:
            raise MeetingError(f"Zoom refused the credentials ({response.status_code}): {response.text[:200]}")
        body = response.json()
        self._token = body["access_token"]
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 3600))
        return self._token

    async def create(
        self,
        *,
        topic: str,
        start: datetime,
        duration_minutes: int,
        timezone: str,
        invitee_email: str | None = None,
    ) -> MeetingLink:
        if not self.is_configured():
            raise MeetingNotConfigured("Zoom needs ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET")

        s = get_settings()
        # Zoom wants the local wall-clock time plus a separate timezone field.
        local = start.astimezone(_zone(timezone)).strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "topic": topic,
            "type": 2,  # scheduled meeting
            "start_time": local,
            "timezone": timezone,
            "duration": duration_minutes,
            "settings": {
                "join_before_host": True,
                "waiting_room": False,
                "approval_type": 2,  # no registration
                "mute_upon_entry": False,
            },
        }

        async with httpx.AsyncClient(timeout=15) as client:
            token = await self._access_token(client)
            response = await client.post(
                f"{API_BASE}/users/{s.zoom_host_user}/meetings",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code not in (200, 201):
            raise MeetingError(f"Zoom could not create the meeting ({response.status_code}): {response.text[:300]}")

        body = response.json()
        url = body.get("join_url")
        if not url:
            raise MeetingError(f"Zoom created a meeting but returned no join_url: {body}")
        logger.info("Zoom meeting %s created for %s", body.get("id"), local)
        return MeetingLink(provider=self.name, url=url, meeting_id=str(body.get("id", "")))


def _zone(name: str):
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ModuleNotFoundError):
        return timezone(timedelta(hours=5, minutes=30), "IST")
