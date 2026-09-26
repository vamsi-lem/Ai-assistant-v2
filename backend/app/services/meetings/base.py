"""
The meeting-link contract.

A provider is given a slot and returns a link. That is all the rest of the
system knows. Zoom and Google Meet are two files in this folder; adding
Microsoft Teams is a third file and one line in service.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class MeetingError(Exception):
    """The provider was reached and refused, or failed."""


class MeetingNotConfigured(Exception):
    """No provider, or a provider missing its credentials."""


@dataclass(frozen=True)
class MeetingLink:
    provider: str
    url: str
    meeting_id: str


class MeetingProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    async def create(
        self,
        *,
        topic: str,
        start: datetime,
        duration_minutes: int,
        timezone: str,
        invitee_email: str | None = None,
    ) -> MeetingLink:
        """Create a meeting starting at `start` (timezone-aware). Raises MeetingError."""
        ...
