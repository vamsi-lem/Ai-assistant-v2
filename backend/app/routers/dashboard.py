"""
The numbers on the dashboard and the analytics page.

Both are computed inside Postgres by the functions in migration 0004, so
the backend makes one round trip per screen regardless of how many leads
there are. A counsellor's numbers cover only the leads assigned to them.

  GET /api/dashboard/summary   counts, the priority queue, today's sessions
  GET /api/analytics/summary   funnel by stage, sources, call outcomes
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import CurrentUser, require_user
from ..config import get_settings
from ..db import db, execute
from ..schemas import AnalyticsOut, BookingRow, DashboardCounts, DashboardOut, LeadOut
from ..services.scope import assigned_filter, scope_leads

logger = logging.getLogger("backend.dashboard")
router = APIRouter(prefix="/api", tags=["dashboard"])

MIGRATION_HINT = "Run supabase/migrations/0004_dashboard_views.sql in the Supabase SQL editor, then retry."


def _db_failure(exc: Exception, what: str) -> HTTPException:
    text = str(exc) or type(exc).__name__
    logger.exception("%s failed: %s", what, text)
    if "does not exist" in text or "PGRST202" in text or "PGRST205" in text:
        text = f"{MIGRATION_HINT} (database said: {text[:200]})"
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{what} failed: {text[:400]}")


async def _rpc(name: str, params: dict) -> dict:
    result = await execute(db().rpc(name, params))
    data = result.data
    # PostgREST returns a json scalar for a json returning function.
    return data if isinstance(data, dict) else {}


@router.get("/dashboard/summary", response_model=DashboardOut)
async def dashboard_summary(user: CurrentUser = Depends(require_user)) -> DashboardOut:
    settings = get_settings()
    who = assigned_filter(user)

    try:
        counts = await _rpc("dashboard_counts", {"p_assigned": who, "p_tz": settings.booking_timezone})

        queue_q = (
            db()
            .table("lead_overview")
            .select("*")
            .not_.in_("stage", ["converted", "lost"])
            .order("score", desc=True, nullsfirst=False)
            .order("created_at", desc=True)
            .limit(8)
        )
        queue = await execute(scope_leads(queue_q, user))

        now = datetime.now(timezone.utc)
        today_q = (
            db()
            .table("upcoming_bookings")
            .select("*")
            .eq("status", "booked")
            .gte("scheduled_at", (now - timedelta(hours=12)).isoformat())
            .lte("scheduled_at", (now + timedelta(hours=36)).isoformat())
            .order("scheduled_at")
        )
        today_rows = (await execute(today_q)).data or []
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Loading the dashboard") from exc

    # "Today" in the booking timezone, decided here rather than in SQL so the
    # list and the count agree with the clock on the counsellor's wall.
    from .bookings import _zone  # local import avoids a cycle at module load

    zone = _zone()
    today_key = now.astimezone(zone).date()
    today = [
        BookingRow(**row)
        for row in today_rows
        if datetime.fromisoformat(str(row["scheduled_at"]).replace("Z", "+00:00")).astimezone(zone).date() == today_key
        and (user.sees_all_leads or row.get("counsellor_id") == user.id)
    ]

    return DashboardOut(
        scope="all" if who is None else "mine",
        counts=DashboardCounts(**{k: int(v or 0) for k, v in counts.items() if k in DashboardCounts.model_fields}),
        queue=[LeadOut(**row) for row in (queue.data or [])],
        today=today,
    )


@router.get("/analytics/summary", response_model=AnalyticsOut)
async def analytics_summary(user: CurrentUser = Depends(require_user)) -> AnalyticsOut:
    who = assigned_filter(user)
    try:
        data = await _rpc("analytics_summary", {"p_assigned": who})
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Loading analytics") from exc

    total = int(data.get("total") or 0)
    converted = int(data.get("converted") or 0)
    sources = list(data.get("sources") or [])
    return AnalyticsOut(
        total=total,
        converted=converted,
        conversion_rate=round(converted * 100 / total) if total else 0,
        funnel=list(data.get("funnel") or []),
        sources=sources,
        calls=list(data.get("calls") or []),
        top_source=sources[0]["source"] if sources else None,
    )
