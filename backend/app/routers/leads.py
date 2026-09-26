"""
Lead intake. The entry point for the whole pipeline.

The ordering here is the one rule that must not be broken: the lead is written
to the database BEFORE any call is attempted. A carrier outage, a compliance
block or a bad number must never cost you the lead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import throttle
from ..config import get_settings
from ..db import get_by_id, insert_one, update_by_id
from ..deps import client_ip, require_agent_key
from ..schemas import (
    BrowserJoin,
    CallOut,
    LeadCallbackUpdate,
    LeadCreate,
    LeadCreateResponse,
    LeadOut,
)
from ..services import livekit_service
from ..services.telephony import service as telephony
from ..services.telephony.base import TelephonyError, TelephonyNotConfigured

logger = logging.getLogger("backend.leads")
router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.post("", response_model=LeadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadCreate, request: Request) -> LeadCreateResponse:
    settings = get_settings()

    # ---- 0. One brake before anything is written. ------------------------
    # A flood from one address is not a set of leads, so it is refused before
    # the database is touched. Real people never reach this limit.
    if not throttle.check_ip(client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many submissions from this connection. Please try again in an hour.",
        )

    # ---- 1. Save the lead. Always. ---------------------------------------
    now = datetime.now(timezone.utc).isoformat()

    lead_row = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "product_or_course": payload.product_or_course,
        "notes": payload.notes,
        "source": "form",
        "status": "new",
        "consent_given": payload.consent_given,
        # Consent evidence is written at the same instant as the lead so the
        # two can never disagree.
        "consent_at": now if payload.consent_given else None,
        "consent_ip": client_ip(request) if payload.consent_given else None,
        "consent_text": payload.consent_text if payload.consent_given else None,
    }

    try:
        lead = await insert_one("leads", lead_row)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not save lead")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not save the lead: {exc}",
        ) from exc

    lead_id = lead["id"]
    logger.info("Lead %s saved (%s, %s)", lead_id, payload.name, payload.product_or_course)

    # ---- 2. No consent means no call. Stop here, cleanly. -----------------
    if not payload.consent_given:
        logger.info("Lead %s has no consent. Saved, not called.", lead_id)
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=None,
            call_skipped_reason=(
                "Saved, but no call was placed because consent was not given."
            ),
        )

    # ---- 2b. Same number called minutes ago: keep the lead, skip the call. --
    try:
        last = await throttle.recent_call_to(payload.phone)
    except Exception:  # noqa: BLE001
        # A failed lookup must not block a real lead; log it and carry on.
        logger.exception("Phone cooldown lookup failed; proceeding without it")
        last = None
    if last is not None:
        minutes_ago = max(1, int((datetime.now(timezone.utc) - last).total_seconds() // 60))
        reason = (
            f"Saved, but not called: this number was already called {minutes_ago} minute(s) ago. "
            f"A second call is allowed after {settings.lead_phone_cooldown_minutes} minutes."
        )
        logger.info("Lead %s not called: %s", lead_id, reason)
        # Status stays 'new' (the schema's list has no 'duplicate'); the note
        # tells a counsellor reading the row why no call followed.
        existing = (lead.get("notes") or "").strip()
        note = "[system] Repeat submission inside the call cooldown; not called again."
        lead = (
            await update_by_id(
                "leads", lead_id, {"notes": f"{existing}\n{note}".strip() if existing else note}
            )
            or lead
        )
        return LeadCreateResponse(lead=LeadOut(**lead), call=None, call_skipped_reason=reason)

    # ---- 3. Create the call record, which fixes the room name. ------------
    call = await insert_one(
        "calls",
        {
            "lead_id": lead_id,
            "status": "queued",
            "transport": settings.call_transport,
        },
    )
    call_id = call["id"]

    # The room name is derived from the call id, so it can only be set now.
    room_name = livekit_service.room_name_for_call(call_id)
    call = await update_by_id("calls", call_id, {"room_name": room_name}) or call

    # ---- 4a. Browser path: hand the frontend a token and we are done. -----
    if settings.call_transport == "browser":
        token = livekit_service.create_browser_token(call_id, payload.name)
        call = await update_by_id("calls", call_id, {"status": "ringing"}) or call
        await update_by_id("leads", lead_id, {"status": "calling"})

        logger.info("Call %s ready for browser join in room %s", call_id, room_name)
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=CallOut(**call),
            join=BrowserJoin(url=settings.livekit_url, token=token, room_name=room_name),
        )

    # ---- 4b. Phone path: ask the carrier to dial. -------------------------
    try:
        placed = await telephony.place_call(
            to_number=payload.phone, call_id=call_id, lead=lead
        )
    except telephony.ComplianceBlock as exc:
        # Not an error in the system. A deliberate refusal.
        logger.warning("Call %s blocked on compliance: %s", call_id, exc)
        await update_by_id("calls", call_id, {"status": "failed", "error": str(exc)})
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=CallOut(**(await get_by_id("calls", call_id) or call)),
            call_skipped_reason=str(exc),
        )
    except TelephonyNotConfigured as exc:
        # The lead is safe in the database. Say plainly that nothing dialled.
        logger.warning("Call %s not placed: %s", call_id, exc)
        await update_by_id("calls", call_id, {"status": "failed", "error": str(exc)})
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=CallOut(**(await get_by_id("calls", call_id) or call)),
            call_skipped_reason=str(exc),
        )
    except TelephonyError as exc:
        logger.error("Call %s rejected by carrier: %s", call_id, exc)
        await update_by_id("calls", call_id, {"status": "failed", "error": str(exc)})
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=CallOut(**(await get_by_id("calls", call_id) or call)),
            call_skipped_reason=str(exc),
        )

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

    return LeadCreateResponse(lead=LeadOut(**lead), call=CallOut(**call))


@router.get("/{lead_id}", response_model=LeadOut)
async def read_lead(lead_id: str) -> LeadOut:
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return LeadOut(**lead)


@router.patch(
    "/{lead_id}/callback",
    response_model=LeadOut,
    dependencies=[Depends(require_agent_key)],
)
async def save_callback(lead_id: str, payload: LeadCallbackUpdate) -> LeadOut:
    """
    The agent calls this the moment the lead names a callback time, not at
    the end of the call. If the line drops ten seconds later, the time is
    already saved. Agent-only, behind the shared secret.
    """
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    # Appended to the existing notes column rather than new columns, so the
    # schema from 0001_init.sql is all that is ever required.
    lines: list[str] = []
    if payload.callback_time and payload.callback_time.strip():
        lines.append(f"Callback requested: {payload.callback_time.strip()}")
    if payload.callback_notes and payload.callback_notes.strip():
        lines.append(f"Asked on the call: {payload.callback_notes.strip()}")

    changes: dict = {}
    if lines:
        existing = (lead.get("notes") or "").strip()
        stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
        addition = f"[Maya {stamp}] " + " | ".join(lines)
        changes["notes"] = f"{existing}\n{addition}".strip() if existing else addition
        changes["status"] = "contacted"
        lead = await update_by_id("leads", lead_id, changes) or lead

    logger.info("Lead %s callback saved: %s", lead_id, changes)
    return LeadOut(**lead)
