"""
Health check.

Deliberately more than a 200. It reports what the server actually believes
about itself: whether the database answers, which transport is live, whether
the carrier is configured, and whether agent authentication is on. Most of the
time lost in v1 went on config that was wrong in a way nothing announced.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..db import check_db
from ..schemas import HealthOut
from ..services.telephony import service as telephony

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    settings = get_settings()
    db_ok, db_detail = await check_db()

    return HealthOut(
        status="ok" if db_ok else "degraded",
        env=settings.env,
        database=db_detail,
        transport=settings.describe_transport(),
        telephony=telephony.describe(),
        agent_auth="configured" if settings.agent_api_key else "NOT CONFIGURED",
    )
