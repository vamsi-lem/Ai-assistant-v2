"""
The meetings façade. Routers call this and nothing else.

Two platforms can be live at once. MEETING_PROVIDER names the default; any
other platform with credentials in backend/.env is also offered. The lead
picks on the call ("Google Meet or Zoom?"); "anything is fine" means the
default. A choice that is not configured falls back to the default, and the
caller is told so it can be honest with the lead.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ...config import get_settings
from .base import MeetingLink, MeetingNotConfigured, MeetingProvider
from .google_meet import GoogleMeetProvider
from .zoom import ZoomProvider

logger = logging.getLogger("backend.meetings")

_PROVIDERS: dict[str, MeetingProvider] = {
    "zoom": ZoomProvider(),
    "google": GoogleMeetProvider(),
}

# What a lead might say, mapped to a platform name.
_ALIASES: dict[str, str] = {
    "zoom": "zoom",
    "google": "google",
    "google meet": "google",
    "meet": "google",
    "gmeet": "google",
    "google_meet": "google",
    "googlemeet": "google",
}

LABELS = {"zoom": "Zoom", "google": "Google Meet"}


def available() -> list[str]:
    """Configured platforms, default first."""
    return [p for p in get_settings().meeting_platforms() if _PROVIDERS[p].is_configured()]


def enabled() -> bool:
    return bool(available())


def normalise(requested: str | None) -> str | None:
    """'Google Meet', 'zoom', 'any' -> 'google', 'zoom', None."""
    if not requested:
        return None
    return _ALIASES.get(requested.strip().lower())


def choose(requested: str | None) -> tuple[str, str | None]:
    """
    Which platform to use for this booking, and a note if it is not the one
    the lead asked for. Raises MeetingNotConfigured when nothing is set up.
    """
    platforms = available()
    if not platforms:
        raise MeetingNotConfigured(
            "No meeting platform is configured. Set MEETING_PROVIDER and its credentials in backend/.env."
        )
    wanted = normalise(requested)
    if wanted is None or wanted in platforms:
        return wanted or platforms[0], None
    return platforms[0], f"{LABELS[wanted]} is not set up; a {LABELS[platforms[0]]} link was created instead."


def get_provider(name: str) -> MeetingProvider:
    provider = _PROVIDERS.get(name)
    if provider is None or not provider.is_configured():
        raise MeetingNotConfigured(f"{name} is not configured in backend/.env")
    return provider


async def create_meeting(
    *,
    topic: str,
    start: datetime,
    duration_minutes: int,
    timezone: str,
    invitee_email: str | None = None,
    platform: str | None = None,
) -> tuple[MeetingLink, str | None]:
    """
    Create the meeting on the chosen platform. Returns the link and a note
    when the lead's choice could not be honoured. Raises MeetingNotConfigured
    or MeetingError. Never returns a fake link.
    """
    name, note = choose(platform)
    link = await get_provider(name).create(
        topic=topic,
        start=start,
        duration_minutes=duration_minutes,
        timezone=timezone,
        invitee_email=invitee_email,
    )
    return link, note
