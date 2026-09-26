"""
The telephony contract.

Everything above this layer talks in these terms and never imports a carrier
SDK. Swapping Plivo for Exotel is a new file in this folder plus one line in
service.py, and nothing else in the codebase changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TelephonyNotConfigured(Exception):
    """
    Raised when a call is requested but the provider has no credentials.

    Deliberately an exception rather than a fake success. A silent no-op here
    would show a lead as "calling" in the database while nothing dialled, which
    is far worse than a visible error.
    """


class TelephonyError(Exception):
    """The provider was reached and refused, or failed."""


@dataclass(frozen=True)
class PlacedCall:
    """What a provider returns after accepting a dial request."""

    provider: str
    provider_call_id: str
    status: str  # our vocabulary, not the provider's


@dataclass(frozen=True)
class CallStatus:
    """Normalised status, used by both webhooks and polling."""

    status: str
    error: str | None = None


class TelephonyProvider(Protocol):
    """What every carrier implementation must offer."""

    name: str

    def is_configured(self) -> bool:
        """True when this provider has everything it needs to place a call."""
        ...

    def describe(self) -> str:
        """One line for the boot log and the health endpoint."""
        ...

    async def place_call(self, *, to_number: str, call_id: str, lead_name: str = "") -> PlacedCall:
        """
        Dial `to_number` into the room for `call_id`. Returns as soon as the
        dial is accepted; answering is watched by the agent. Raises
        TelephonyNotConfigured or TelephonyError.
        """
        ...

    async def fetch_status(self, provider_call_id: str, *, call_id: str | None = None) -> CallStatus:
        """
        Ask where a call is: ringing, in progress, or over. Used by the
        status endpoint the frontend polls.
        """
        ...

    def verify_webhook(self, *, url: str, body: bytes, headers: dict[str, str]) -> bool:
        """
        Confirm a status callback really came from this provider.

        A webhook endpoint is a public URL that mutates call state, so an
        unverified one lets anyone mark any call completed.
        """
        ...


# Provider status strings mapped to ours. Anything unrecognised becomes
# 'in-progress' rather than being dropped, so an unexpected value never
# silently strands a call in the wrong state.
STATUS_VOCABULARY = {
    "queued",
    "ringing",
    "in-progress",
    "completed",
    "failed",
    "no-answer",
    "busy",
}


def normalise_status(raw: str) -> str:
    value = (raw or "").strip().lower().replace("_", "-")
    return value if value in STATUS_VOCABULARY else "in-progress"
