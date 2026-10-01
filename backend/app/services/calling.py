"""
Placing a call to a lead.

One function, used by the public form, by "call again" on the lead page and
by anything else that ever needs Maya to ring someone. The lead row must
already exist: the caller saves first, then asks for the call.

What happens, in order:
  1. the call row is created, which fixes the room name call-<id>
  2. browser transport: a join token is minted (testing without a carrier)
     phone transport: the carrier is asked to dial through LiveKit
  3. the lead's status moves to "calling" and a call_started event is written

Every refusal (no consent, compliance block, carrier not configured, carrier
error) is written on the call row and returned as a reason, never raised.
The lead is never lost because a call did not happen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..db import get_by_id, insert_one, update_by_id
from . import events, livekit_service
from .telephony import service as telephony
from .telephony.base import TelephonyError, TelephonyNotConfigured

logger = logging.getLogger("backend.calling")


@dataclass
class Placed:
    call: dict[str, Any] | None
    skipped_reason: str | None = None
    # Browser transport only: what the page needs to join the room.
    join: dict[str, str] | None = None


async def place_call(lead: dict[str, Any], *, actor_id: str | None = None, trigger: str = "form") -> Placed:
    settings = get_settings()
    lead_id = lead["id"]

    if not lead.get("consent_given"):
        return Placed(call=None, skipped_reason="No call was placed because consent was not given.")
    if lead.get("status") == "do_not_call":
        return Placed(call=None, skipped_reason="This lead asked not to be called.")

    # ---- 1. The call row, which fixes the room name. ----------------------
    call = await insert_one(
        "calls",
        {"lead_id": lead_id, "status": "queued", "transport": settings.call_transport},
    )
    call_id = call["id"]
    room_name = livekit_service.room_name_for_call(call_id)
    call = await update_by_id("calls", call_id, {"room_name": room_name}) or call

    # ---- 2a. Browser transport ---------------------------------------------
    if settings.call_transport == "browser":
        token = livekit_service.create_browser_token(call_id, lead["name"])
        call = await update_by_id("calls", call_id, {"status": "ringing"}) or call
        await update_by_id("leads", lead_id, {"status": "calling"})
        await events.record(lead_id, "call_started", f"browser call ({trigger})", actor_id=actor_id, data={"call_id": call_id})
        logger.info("Call %s ready for browser join in room %s", call_id, room_name)
        return Placed(
            call=call,
            join={"url": settings.livekit_url, "token": token, "room_name": room_name},
        )

    # ---- 2b. Phone transport: ask the carrier to dial ------------------------
    try:
        placed = await telephony.place_call(to_number=lead["phone"], call_id=call_id, lead=lead)
    except telephony.ComplianceBlock as exc:
        logger.warning("Call %s blocked on compliance: %s", call_id, exc)
        return await _refused(call_id, lead_id, str(exc))
    except TelephonyNotConfigured as exc:
        logger.warning("Call %s not placed: %s", call_id, exc)
        return await _refused(call_id, lead_id, str(exc))
    except TelephonyError as exc:
        logger.error("Call %s rejected by carrier: %s", call_id, exc)
        return await _refused(call_id, lead_id, str(exc))

    call = (
        await update_by_id(
            "calls",
            call_id,
            {
                "status": placed.status,
                "provider": placed.provider,
                "provider_call_id": placed.provider_call_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        or call
    )
    await update_by_id("leads", lead_id, {"status": "calling"})
    await events.record(
        lead_id,
        "call_started",
        f"Maya is dialling ({trigger})",
        actor_id=actor_id,
        data={"call_id": call_id, "provider": placed.provider},
    )
    return Placed(call=call)


async def _refused(call_id: str, lead_id: str, reason: str) -> Placed:
    await update_by_id("calls", call_id, {"status": "failed", "error": reason})
    await events.record(lead_id, "call_ended", f"not placed: {reason}", data={"call_id": call_id, "status": "failed"})
    return Placed(call=await get_by_id("calls", call_id), skipped_reason=reason)
