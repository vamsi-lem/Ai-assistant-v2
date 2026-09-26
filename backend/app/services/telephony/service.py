"""
The telephony façade.

Routers call this and nothing else. It picks the provider, enforces the two
India compliance rules that must hold before any number is dialled, and gives
one clear answer about whether a call can be placed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ...config import get_settings
from .base import PlacedCall, TelephonyNotConfigured, TelephonyProvider
from .plivo_provider import PlivoProvider

logger = logging.getLogger("backend.telephony")

_PROVIDERS: dict[str, TelephonyProvider] = {
    "plivo": PlivoProvider(),
    # Add ExotelProvider() here to switch carriers. Nothing outside this folder
    # needs to know.
}


def get_provider() -> TelephonyProvider:
    settings = get_settings()
    provider = _PROVIDERS.get(settings.telephony_provider)
    if provider is None:
        raise TelephonyNotConfigured(
            f"Unknown TELEPHONY_PROVIDER '{settings.telephony_provider}'. "
            f"Supported: {', '.join(sorted(_PROVIDERS))}."
        )
    return provider


def describe() -> str:
    settings = get_settings()

    if settings.call_transport == "browser":
        return "browser transport, no carrier in use"
    if not settings.telephony_enabled:
        return "phone transport but TELEPHONY_ENABLED=false, no calls will be placed"

    try:
        return get_provider().describe()
    except TelephonyNotConfigured as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Compliance gate
#
# Two rules, both from India's commercial calling regulations, both checked
# before a single digit is dialled.
# ---------------------------------------------------------------------------


class ComplianceBlock(Exception):
    """The call is technically possible but must not be placed."""


def check_may_call(lead: dict) -> None:
    """
    Raise ComplianceBlock if this lead must not be called.

    Rule 1: no consent, no call. Cold calling is prohibited in India and the
    form submission is what makes this lawful. A lead without recorded consent
    is stored and left alone.

    Rule 2: consent expires. Explicit consent for a service call is valid for
    seven days. After that the lead needs to ask again. CONSENT_WINDOW_DAYS
    makes the window configurable, but do not lengthen it without advice.

    Rule 3: a lead marked do_not_call is never dialled, whatever else is true.
    """
    settings = get_settings()

    if lead.get("status") == "do_not_call":
        raise ComplianceBlock("Lead is marked do_not_call.")

    if not lead.get("consent_given"):
        raise ComplianceBlock(
            "No consent recorded for this lead. India prohibits commercial calls "
            "without explicit consent, so this number will not be dialled."
        )

    consent_at = lead.get("consent_at")
    if consent_at:
        if isinstance(consent_at, str):
            parsed = datetime.fromisoformat(consent_at.replace("Z", "+00:00"))
        else:
            parsed = consent_at
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - parsed
        if age > timedelta(days=settings.consent_window_days):
            raise ComplianceBlock(
                f"Consent is {age.days} days old, beyond the "
                f"{settings.consent_window_days} day window. Ask the lead again "
                "before calling."
            )


async def is_on_dnd(phone: str) -> bool:
    """
    Do-not-call check, run before dialling.

    Plivo publishes no DND filtering for voice, unlike Exotel, so this is our
    job. Right now it returns False, which is honest rather than useful: there
    is no check wired in yet.

    It is NOT a silent stub. The startup log says plainly that DND checking is
    unimplemented, and this must be filled in before calling anyone outside a
    test list. The likely implementations, in order of preference:

      1. Whatever Plivo answers when asked how to scrub against NCPR. Ask them,
         it is one of the three questions in the onboarding ticket.
      2. A commercial DND lookup API.
      3. A suppression table in Supabase that you maintain by hand.

    Option 3 is a day's work and better than nothing. Five complaints from five
    recipients inside ten days bars your number for fifteen days.
    """
    return False


# ---------------------------------------------------------------------------
# Placing a call
# ---------------------------------------------------------------------------


async def place_call(*, to_number: str, call_id: str, lead: dict) -> PlacedCall:
    """
    Dial a lead, having first established that we are allowed to.

    Raises ComplianceBlock, TelephonyNotConfigured or TelephonyError. Never
    returns a fake success.
    """
    settings = get_settings()

    if not settings.telephony_enabled:
        raise TelephonyNotConfigured(
            "TELEPHONY_ENABLED is false. Set it to true in backend/.env once your "
            "carrier account is ready."
        )

    check_may_call(lead)

    if settings.dnd_check_enabled and await is_on_dnd(to_number):
        raise ComplianceBlock(f"{to_number} is on the do-not-call list.")

    provider = get_provider()
    return await provider.place_call(
        to_number=to_number, call_id=call_id, lead_name=str(lead.get("name") or "")
    )
