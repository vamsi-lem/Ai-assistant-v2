"""
The lead timeline.

Every notable thing that happens to a lead is one row in lead_events:
created, called, call ended, booked, WhatsApp sent, stage changed, assigned,
note added. The lead page shows them newest first.

Recording an event is best effort. A timeline write must never fail the
request that caused it, so errors are logged and swallowed here.
"""

from __future__ import annotations

import logging
from typing import Any

from ..db import insert_one

logger = logging.getLogger("backend.events")

KINDS = {
    "lead_created",
    "call_started",
    "call_ended",
    "booking_created",
    "booking_updated",
    "whatsapp_sent",
    "whatsapp_failed",
    "stage_changed",
    "assigned",
    "note_added",
    "callback_noted",
}


async def record(
    lead_id: str,
    kind: str,
    detail: str | None = None,
    *,
    data: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    if kind not in KINDS:
        logger.warning("Unknown event kind %r for lead %s; recording anyway", kind, lead_id)
    payload: dict[str, Any] = dict(data or {})
    if detail:
        payload["detail"] = detail[:500]
    try:
        await insert_one(
            "lead_events",
            {"lead_id": lead_id, "kind": kind, "data": payload, "actor_id": actor_id},
        )
    except Exception as exc:  # noqa: BLE001 - never let the timeline break the request
        logger.warning("Could not record %s for lead %s: %s", kind, lead_id, exc)
