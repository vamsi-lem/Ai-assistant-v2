"""
Google Meet, by creating a Google Calendar event with a Meet link.

Google does not let a plain service account create Meet links on a normal
Gmail account, so this uses OAuth for the counsellor's own Google account:
an OAuth client (Client ID + Secret) and a one-time refresh token obtained
by signing in once. docs/BOOKINGS.md has the five-minute walkthrough. From
then on the backend refreshes access tokens itself and nobody signs in
again.

The event lands on the counsellor's calendar (GOOGLE_CALENDAR_ID, default
"primary") with the lead as an optional attendee, so the counsellor sees
the booking where they already look.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta

import httpx

from ...config import get_settings
from .base import MeetingError, MeetingLink, MeetingNotConfigured

logger = logging.getLogger("backend.meetings.google")

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleMeetProvider:
    name = "google"

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_client_secret and s.google_refresh_token)

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token

        s = get_settings()
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "refresh_token": s.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            raise MeetingError(f"Google refused the refresh token ({response.status_code}): {response.text[:200]}")
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
            raise MeetingNotConfigured(
                "Google Meet needs GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN"
            )

        s = get_settings()
        end = start + timedelta(minutes=duration_minutes)
        event = {
            "summary": topic,
            "start": {"dateTime": start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": timezone},
            "conferenceData": {
                "createRequest": {
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if invitee_email:
            event["attendees"] = [{"email": invitee_email}]

        async with httpx.AsyncClient(timeout=15) as client:
            token = await self._access_token(client)
            response = await client.post(
                f"{CALENDAR_API}/calendars/{s.google_calendar_id}/events",
                params={"conferenceDataVersion": 1, "sendUpdates": "all" if invitee_email else "none"},
                json=event,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code not in (200, 201):
            raise MeetingError(
                f"Google could not create the event ({response.status_code}): {response.text[:300]}"
            )

        body = response.json()
        url = body.get("hangoutLink")
        if not url:
            raise MeetingError("Google created the event but no Meet link came back; is Meet enabled on the account?")
        logger.info("Google Meet %s created for %s", body.get("id"), start.isoformat())
        return MeetingLink(provider=self.name, url=url, meeting_id=str(body.get("id", "")))
