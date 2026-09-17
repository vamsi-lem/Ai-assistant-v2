"""
Call status for the frontend, and call context for the agent.

Two audiences, two levels of trust. The status endpoint is public and returns
only what a progress indicator needs. The context endpoint is agent-only and
returns the lead's name and number, so it is behind the shared-secret guard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import get_settings
from ..db import find_one, get_by_id, update_by_id
from ..deps import require_agent_key
from ..schemas import AgentCallContext, CallOut, CallStatusOut
from ..services.telephony import service as telephony
from ..services.telephony.base import TelephonyNotConfigured

logger = logging.getLogger("backend.calls")
router = APIRouter(prefix="/api/calls", tags=["calls"])

# Statuses that will never change again, so polling should stop.
TERMINAL = {"completed", "failed", "no-answer", "busy"}


@router.get("/{call_id}/status", response_model=CallStatusOut)
async def call_status(call_id: str) -> CallStatusOut:
    """
    Where is this call up to?

    On the phone path, if we have no public URL the carrier cannot send us a
    webhook, so this endpoint asks the carrier directly and writes the answer
    back. That is what makes local development work without a tunnel.
    """
    call = await get_by_id("calls", call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found.")

    settings = get_settings()
    should_poll = (
        call["transport"] == "phone"
        and call.get("provider_call_id")
        and call["status"] not in TERMINAL
        and not settings.public_base_url  # webhooks would handle it otherwise
    )

    if should_poll:
        try:
            fresh = await telephony.get_provider().fetch_status(call["provider_call_id"])
            if fresh.status != call["status"]:
                patch: dict = {"status": fresh.status}
                if fresh.error:
                    patch["error"] = fresh.error
                call = await update_by_id("calls", call_id, patch) or call
        except TelephonyNotConfigured:
            pass  # nothing to poll; the stored status is the best we have
        except Exception as exc:  # noqa: BLE001
            logger.warning("Status poll failed for call %s: %s", call_id, exc)

    conversation = await find_one("conversations", "call_id", call_id)
    messages = (conversation or {}).get("messages") or []

    return CallStatusOut(
        call=CallOut(**call),
        turns=len(messages),
        summary=(conversation or {}).get("summary"),
    )


@router.get(
    "/{call_id}/context",
    response_model=AgentCallContext,
    dependencies=[Depends(require_agent_key)],
)
async def call_context(call_id: str) -> AgentCallContext:
    """
    Everything the agent needs to hold this conversation.

    The agent is stateless by design. It is handed a room named `call-<id>`,
    recovers the id, and calls this. That is the whole reason the same agent
    code serves a browser participant today and a phone participant later.
    """
    call = await get_by_id("calls", call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found.")

    lead = await get_by_id("leads", call["lead_id"])
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call exists but its lead is missing.",
        )

    return AgentCallContext(
        call_id=call["id"],
        lead_id=lead["id"],
        name=lead["name"],
        phone=lead["phone"],
        product_or_course=lead["product_or_course"],
        notes=lead.get("notes"),
        transport=call["transport"],
    )
