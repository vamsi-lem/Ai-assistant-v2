"""
Transcript storage. Written by the agent, never by the browser.

The agent posts the COMPLETE turn list on every flush and we replace the stored
list rather than appending to it. That single choice makes the endpoint
idempotent: a retried request, a duplicated flush, or two flushes racing each
other can never produce duplicate or out-of-order turns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import db, find_one, get_by_id, update_by_id
from ..deps import require_agent_key
from ..schemas import ConversationOut, ConversationUpsert

logger = logging.getLogger("backend.conversations")
router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# When the call reaches one of these, the lead's own status moves with it.
LEAD_STATUS_FOR_CALL = {
    "completed": "contacted",
    "no-answer": "no_answer",
    "busy": "no_answer",
    "failed": "failed",
}


@router.post("", response_model=ConversationOut, dependencies=[Depends(require_agent_key)])
async def upsert_conversation(payload: ConversationUpsert) -> ConversationOut:
    call = await get_by_id("calls", payload.call_id)
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No call with id {payload.call_id}.",
        )

    messages = [
        {
            "role": message.role,
            "text": message.text,
            "at": (message.at or datetime.now(timezone.utc)).isoformat(),
            "interrupted": message.interrupted,
        }
        for message in payload.messages
    ]

    row = {
        "call_id": payload.call_id,
        "messages": messages,
        "summary": payload.summary,
    }

    existing = await find_one("conversations", "call_id", payload.call_id)

    if existing:
        patch: dict = {"messages": messages}
        # Only overwrite the summary when one was actually sent. A mid-call
        # flush passes None and must not wipe a summary written earlier.
        if payload.summary is not None:
            patch["summary"] = payload.summary
        conversation = await update_by_id("conversations", existing["id"], patch)
    else:
        result = await db().table("conversations").insert(row).execute()
        conversation = result.data[0] if result.data else None

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not store the transcript.",
        )

    # The agent can advance the call in the same request, saving a round trip
    # on a path that runs during a live conversation.
    if payload.call_status:
        call_patch: dict = {"status": payload.call_status}
        if payload.call_status in LEAD_STATUS_FOR_CALL:
            call_patch["ended_at"] = datetime.now(timezone.utc).isoformat()

        await update_by_id("calls", payload.call_id, call_patch)

        lead_status = LEAD_STATUS_FOR_CALL.get(payload.call_status)
        if lead_status:
            await update_by_id("leads", call["lead_id"], {"status": lead_status})

    logger.info(
        "Stored %d turn(s) for call %s%s",
        len(messages),
        payload.call_id,
        f", status -> {payload.call_status}" if payload.call_status else "",
    )

    return ConversationOut(**conversation)


@router.get("/{call_id}", response_model=ConversationOut, dependencies=[Depends(require_agent_key)])
async def read_conversation(call_id: str) -> ConversationOut:
    conversation = await find_one("conversations", "call_id", call_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation stored for that call.",
        )
    return ConversationOut(**conversation)
