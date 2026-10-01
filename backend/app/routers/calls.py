"""
Calls: status for the form page, context for the agent, lists and
transcripts for the dashboard.

Three audiences, three levels of trust. The status endpoint is public and
returns only what a progress indicator needs. The context endpoint is agent
only and returns the lead's name and number, so it is behind the shared
secret. The list and detail endpoints need a signed in user, and a
counsellor sees only calls to leads assigned to them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import CurrentUser, require_user
from ..db import db, execute, find_one, get_by_id, update_by_id
from ..deps import require_agent_key
from ..schemas import AgentCallContext, CallDetailOut, CallOut, CallPage, CallStatusOut
from ..services.scope import scope_leads
from ..services.meetings import service as meetings
from ..services.telephony import service as telephony
from ..services.telephony.base import TelephonyNotConfigured

logger = logging.getLogger("backend.calls")
router = APIRouter(prefix="/api/calls", tags=["calls"])

# Statuses that will never change again, so polling should stop.
TERMINAL = {"completed", "failed", "no-answer", "busy"}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("", response_model=CallPage)
async def list_calls(
    user: CurrentUser = Depends(require_user),
    lead_id: str | None = Query(default=None),
    call_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CallPage:
    query = db().table("call_overview").select("*", count="exact")
    query = scope_leads(query, user, column="lead_assigned_to")
    if lead_id:
        query = query.eq("lead_id", lead_id)
    if call_status:
        query = query.eq("status", call_status)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    try:
        result = await execute(query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Loading calls failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Loading calls failed: {exc}")
    return CallPage(items=[CallDetailOut(**row) for row in (result.data or [])], total=result.count or 0)


@router.get("/{call_id}", response_model=CallDetailOut)
async def call_detail(call_id: str, user: CurrentUser = Depends(require_user)) -> CallDetailOut:
    """One call with its full transcript."""
    result = await execute(db().table("call_overview").select("*").eq("id", call_id).maybe_single())
    row = result.data if result and result.data else None
    if not row or (not user.sees_all_leads and row.get("lead_assigned_to") != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found.")
    conversation = await find_one("conversations", "call_id", call_id)
    return CallDetailOut(**row, transcript=(conversation or {}).get("messages") or [])


# ---------------------------------------------------------------------------
# Form page
# ---------------------------------------------------------------------------


@router.get("/{call_id}/status", response_model=CallStatusOut)
async def call_status(call_id: str) -> CallStatusOut:
    """
    Where is this call up to?

    On the phone path this asks LiveKit where the SIP leg is (ringing,
    active, hung up) and writes the answer back, until the agent records the
    final status itself. No webhook and no public URL involved.
    """
    call = await get_by_id("calls", call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found.")

    should_poll = (
        call["transport"] == "phone"
        and call.get("provider_call_id")
        and call["status"] not in TERMINAL
    )

    if should_poll:
        try:
            fresh = await telephony.get_provider().fetch_status(
                call["provider_call_id"], call_id=call_id
            )
            # "completed" from a vanished room never overrides a more specific
            # final status the agent already wrote.
            if fresh.status != call["status"] and not (
                fresh.status == "completed" and call["status"] in TERMINAL
            ):
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
        email=lead.get("email"),
        meeting_platforms=meetings.available(),
    )
