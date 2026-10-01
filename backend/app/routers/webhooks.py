"""
Carrier callbacks.

One endpoint, public, phone path only:

  /api/webhooks/telephony      the carrier tells us how a call ended

On the LiveKit SIP path this is not needed at all: LiveKit reports the phone
leg's status and the agent writes the final one. It stays for Plivo Voice API
callbacks, and because it is a public URL that affects call state it verifies
the carrier's signature before believing a word.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from ..config import get_settings
from ..db import find_one, update_by_id
from ..services import events
from ..services.telephony import service as telephony
from ..services.telephony.base import normalise_status

logger = logging.getLogger("backend.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

LEAD_STATUS_FOR_CALL = {
    "completed": "contacted",
    "no-answer": "no_answer",
    "busy": "no_answer",
    "failed": "failed",
}


@router.post("/telephony")
async def telephony_status(request: Request) -> dict:
    """
    How the call ended.

    Verified before trusted. Without the signature check, anyone who found this
    URL could mark any call completed, or failed, at will.
    """
    settings = get_settings()
    body = await request.body()

    # Reconstruct the URL the carrier signed. Behind a proxy the scheme the
    # socket sees is http, so prefer the configured public URL.
    if settings.public_base_url:
        signed_url = f"{settings.public_base_url}{request.url.path}"
    else:
        signed_url = str(request.url).split("?")[0]

    provider = telephony.get_provider()
    headers = dict(request.headers)

    if not provider.verify_webhook(url=signed_url, body=body, headers=headers):
        logger.warning("Rejected an unverified %s webhook", provider.name)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature verification failed.",
        )

    # Plivo posts form-encoded, not JSON.
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}

    provider_call_id = (
        payload.get("CallUUID")
        or payload.get("call_uuid")
        or payload.get("RequestUUID")
        or payload.get("request_uuid")
        or ""
    )
    raw_status = payload.get("CallStatus") or payload.get("call_status") or ""

    if not provider_call_id:
        logger.warning("Telephony webhook had no call id: %s", payload)
        return {"received": True, "matched": False}

    # Find our call by the carrier's own id for it.
    call = await find_one("calls", "provider_call_id", provider_call_id)
    if not call:
        logger.info("Webhook for a call we do not have: %s", provider_call_id)
        return {"received": True, "matched": False}

    new_status = normalise_status(raw_status)
    patch: dict = {"status": new_status}

    hangup_cause = payload.get("HangupCause") or payload.get("hangup_cause")
    if new_status in ("failed", "no-answer", "busy") and hangup_cause:
        patch["error"] = hangup_cause

    if new_status in LEAD_STATUS_FOR_CALL:
        patch["ended_at"] = datetime.now(timezone.utc).isoformat()

    await update_by_id("calls", call["id"], patch)

    lead_status = LEAD_STATUS_FOR_CALL.get(new_status)
    if lead_status:
        await update_by_id("leads", call["lead_id"], {"status": lead_status})
        await events.record(
            call["lead_id"], "call_ended", f"{new_status} (carrier)",
            data={"call_id": call["id"], "status": new_status},
        )

    logger.info("Call %s -> %s (carrier said '%s')", call["id"], new_status, raw_status)
    return {"received": True, "matched": True, "status": new_status}
