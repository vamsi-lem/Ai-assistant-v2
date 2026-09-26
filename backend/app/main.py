"""
FastAPI application.

Run locally:
    uvicorn app.main:app --reload --port 8000

In a container (Render, Fly) the Dockerfile runs:
    uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import bookings, calls, conversations, health, leads, webhooks
from .services.telephony import service as telephony

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()

    # Say out loud what this server believes, every time it starts. In v1 the
    # single most expensive bug was a call that never happened because
    # telephony was disabled and nothing said so.
    logger.info("Environment      %s", settings.env)
    logger.info("Call transport   %s", settings.describe_transport())
    logger.info("Telephony        %s", telephony.describe())
    logger.info("Webhooks         %s", settings.describe_webhooks())
    logger.info("Agent auth       %s", "configured" if settings.agent_api_key else "NOT CONFIGURED")
    logger.info("Bookings         %s", settings.describe_bookings())
    logger.info("CORS allowed     %s", ", ".join(settings.cors_origins))
    logger.info(
        "Form brakes      %s per address per hour, %s minute gap per number",
        settings.lead_max_per_ip_per_hour or "unlimited",
        settings.lead_phone_cooldown_minutes or "no",
    )

    if settings.dnd_check_enabled:
        logger.warning(
            "DND checking is ENABLED but is_on_dnd() is not implemented yet and "
            "always returns False. Wire it up before calling anyone outside a "
            "test list. See services/telephony/service.py."
        )

    yield

    logger.info("Shutting down")


app = FastAPI(
    title="AI Voice Platform v2",
    description=(
        "Lead capture to AI voice conversation. Supabase for storage, LiveKit "
        "for the room, Sarvam for the voice, Plivo for the phone line."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

_settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    # X-Agent-Key is listed so a browser preflight does not reject it, though
    # only the agent ever sends it.
    allow_headers=["Content-Type", "X-Agent-Key", "X-Dashboard-Key"],
)

app.include_router(health.router)
app.include_router(leads.router)
app.include_router(calls.router)
app.include_router(conversations.router)
app.include_router(webhooks.router)
app.include_router(bookings.router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "ai-voice-platform-v2 backend",
        "health": "/api/health",
        "docs": "/docs",
    }
