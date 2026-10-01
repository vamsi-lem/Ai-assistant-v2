"""
What the dashboard shows under Settings, Voice AI.

Half of Maya's configuration lives in the backend (bookings, meeting links,
WhatsApp, call transport) and half in the agent (name, languages, voice,
brain). The agent reports its half here when it starts, and the dashboard
reads the merged view. Read only for now: editing arrives with the tenants
table (docs/MULTI-TENANT.md).

  GET  /api/settings/voice   dashboard, admins and managers
  POST /api/agent/config     agent, at startup
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_manager
from ..config import get_settings
from ..db import db, execute
from ..deps import require_agent_key
from ..schemas import AgentConfigReport, VoiceSettingsOut

logger = logging.getLogger("backend.settings")
router = APIRouter(prefix="/api", tags=["settings"])

AGENT_KEY = "agent"


@router.post("/agent/config", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_agent_key)])
async def report_agent_config(payload: AgentConfigReport) -> None:
    value = {**payload.model_dump(), "reported_at": datetime.now(timezone.utc).isoformat()}
    try:
        await execute(db().table("app_settings").upsert({"key": AGENT_KEY, "value": value, "updated_at": value["reported_at"]}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not store the agent's configuration report: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not store the report: {exc}")
    logger.info("Agent reported its configuration: %s", payload.model_dump())


@router.get("/settings/voice", response_model=VoiceSettingsOut, dependencies=[Depends(require_manager)])
async def voice_settings() -> VoiceSettingsOut:
    settings = get_settings()
    agent: dict = {}
    try:
        result = await execute(db().table("app_settings").select("value").eq("key", AGENT_KEY).maybe_single())
        agent = (result.data or {}).get("value") or {} if result else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read the agent's configuration report: %s", exc)

    platforms = settings.meeting_platforms()
    reported_at = agent.get("reported_at")
    return VoiceSettingsOut(
        agent_name=agent.get("agent_name") or "",
        company=agent.get("company") or settings.company_name,
        flow=agent.get("flow") or "",
        languages=list(agent.get("languages") or []),
        greeting_language=agent.get("greeting_language") or "",
        tts_model=agent.get("tts_model") or "",
        tts_speaker=agent.get("tts_speaker") or "",
        llm_provider=agent.get("llm_provider") or "",
        llm_model=agent.get("llm_model") or "",
        counsellor_hours=agent.get("counsellor_hours")
        or f"{settings.counsellor_work_start}:00 to {settings.counsellor_work_end}:00, days {','.join(str(d) for d in settings.counsellor_work_days)}",
        booking_timezone=settings.booking_timezone,
        meeting_provider=", ".join(platforms) if platforms else "none",
        whatsapp_template=f"{settings.whatsapp_template_name} ({settings.whatsapp_provider})" if settings.whatsapp_provider != "none" else "none",
        call_transport=settings.describe_transport(),
        agent_reported_at=datetime.fromisoformat(reported_at) if reported_at else None,
    )
