"""
Environment configuration for the backend.

Everything read from the environment lands here and is validated once at
import time, so a misconfiguration is a clear message at startup rather than a
500 halfway through a lead submission.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# app/config.py -> app/ -> backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_TRUTHY = {"1", "true", "yes", "on"}


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _bool(name: str, default: bool) -> bool:
    raw = _str(name)
    if raw == "":
        return default
    return raw.lower() in _TRUTHY


def _int(name: str, default: int) -> int:
    try:
        return int(_str(name))
    except ValueError:
        return default


def _csv(name: str, default: str) -> list[str]:
    raw = _str(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


class Settings:
    """Read once, use everywhere. Instantiated by get_settings() below."""

    def __init__(self) -> None:
        self.env: str = _str("APP_ENV", "development")
        self.port: int = _int("PORT", 8000)
        self.cors_origins: list[str] = _csv("CORS_ORIGINS", "http://localhost:5173")

        # --- Supabase -------------------------------------------------------
        # The SECRET key, not the anon key. It bypasses row level security,
        # which is exactly why it must never reach a browser.
        self.supabase_url: str = _str("SUPABASE_URL")
        self.supabase_secret_key: str = _str("SUPABASE_SECRET_KEY")

        # --- LiveKit --------------------------------------------------------
        self.livekit_url: str = _str("LIVEKIT_URL")
        self.livekit_api_key: str = _str("LIVEKIT_API_KEY")
        self.livekit_api_secret: str = _str("LIVEKIT_API_SECRET")

        # --- Agent authentication -------------------------------------------
        # Shared secret the agent presents on X-Agent-Key. Generate with:
        #   python -c "import secrets; print(secrets.token_urlsafe(32))"
        self.agent_api_key: str = _str("AGENT_API_KEY")

        # --- Call routing ---------------------------------------------------
        # browser: the lead joins the LiveKit room over WebRTC. No carrier, no
        #          cost, works today.
        # phone:   the carrier dials their mobile and bridges it in. Needs a
        #          configured provider below.
        self.call_transport: str = _str("CALL_TRANSPORT", "browser").lower()

        # --- Telephony ------------------------------------------------------
        self.telephony_enabled: bool = _bool("TELEPHONY_ENABLED", False)
        self.telephony_provider: str = _str("TELEPHONY_PROVIDER", "plivo").lower()

        self.plivo_auth_id: str = _str("PLIVO_AUTH_ID")
        self.plivo_auth_token: str = _str("PLIVO_AUTH_TOKEN")
        self.plivo_from_number: str = _str("PLIVO_FROM_NUMBER")
        self.livekit_sip_trunk_id: str = _str("LIVEKIT_SIP_TRUNK_ID")
        self.livekit_sip_uri: str = _str("LIVEKIT_SIP_URI")

        # Public base URL of THIS backend, used to build webhook callback URLs.
        # On Railway this is your generated domain. Leave blank locally and the
        # status-polling path is used instead.
        self.public_base_url: str = _str("PUBLIC_BASE_URL").rstrip("/")

        # --- Compliance -----------------------------------------------------
        # When on, a number on the do-not-call list is never dialled unless the
        # lead has a recorded consent timestamp inside the window below.
        self.dnd_check_enabled: bool = _bool("DND_CHECK_ENABLED", True)
        self.consent_window_days: int = _int("CONSENT_WINDOW_DAYS", 7)

    # -- validation ---------------------------------------------------------

    def missing(self) -> list[str]:
        """Required variables that are absent, given the choices made above."""
        missing: list[str] = []

        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_secret_key:
            missing.append("SUPABASE_SECRET_KEY")
        if not self.agent_api_key:
            missing.append("AGENT_API_KEY")

        # LiveKit is needed on both transports: browser needs a join token,
        # phone needs the room created before the carrier dials into it.
        if not self.livekit_url:
            missing.append("LIVEKIT_URL")
        if not self.livekit_api_key:
            missing.append("LIVEKIT_API_KEY")
        if not self.livekit_api_secret:
            missing.append("LIVEKIT_API_SECRET")

        if self.call_transport == "phone" and self.telephony_enabled:
            if self.telephony_provider == "plivo":
                if not self.plivo_auth_id:
                    missing.append("PLIVO_AUTH_ID")
                if not self.plivo_auth_token:
                    missing.append("PLIVO_AUTH_TOKEN")
                if not self.plivo_from_number:
                    missing.append("PLIVO_FROM_NUMBER")
                if not self.livekit_sip_uri:
                    missing.append("LIVEKIT_SIP_URI")

        return missing

    # -- human readable status, printed at boot ------------------------------

    def describe_transport(self) -> str:
        if self.call_transport == "browser":
            return "browser (WebRTC). No carrier involved, no per-minute cost."
        if not self.telephony_enabled:
            return "phone, but TELEPHONY_ENABLED=false. No call will be placed."
        return f"phone via {self.telephony_provider} from {self.plivo_from_number or 'UNSET'}"

    def describe_webhooks(self) -> str:
        if self.public_base_url:
            return f"webhooks -> {self.public_base_url}/api/webhooks/telephony"
        return "no PUBLIC_BASE_URL set, falling back to status polling"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    gaps = settings.missing()

    if gaps:
        print("\nThe backend cannot start. Missing in backend/.env:\n", file=sys.stderr)
        for name in gaps:
            print(f"  - {name}", file=sys.stderr)
        print(f"\nFile checked: {ENV_PATH}", file=sys.stderr)
        print("Copy backend/.env.example to backend/.env and fill it in.\n", file=sys.stderr)
        raise SystemExit(1)

    if settings.call_transport not in ("browser", "phone"):
        print(
            f"\nCALL_TRANSPORT must be 'browser' or 'phone', got '{settings.call_transport}'.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return settings
