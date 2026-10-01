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
        self.cors_origins: list[str] = _csv("CORS_ORIGINS", "http://localhost:3000")

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
        # The LiveKit OUTBOUND trunk that points at Plivo (ST_...). LiveKit
        # dials the lead through it; this is the only carrier wiring needed.
        self.livekit_sip_trunk_id: str = _str("LIVEKIT_SIP_TRUNK_ID")
        # Only for the inbound direction (a lead calling Maya). Unused today.
        self.livekit_sip_uri: str = _str("LIVEKIT_SIP_URI")

        # Public base URL of THIS backend. Not needed for calls (LiveKit
        # reports status directly); only for optional Plivo webhooks.
        self.public_base_url: str = _str("PUBLIC_BASE_URL").rstrip("/")

        # --- Bookings: slot, meeting link, WhatsApp --------------------------
        #
        # When Maya books a counsellor slot, the backend creates a meeting
        # link and sends it to the lead on WhatsApp. Each part is a switchable
        # provider and each is optional: with a provider set to "none" the
        # booking is still saved and shown on the counsellor dashboard, and
        # the dashboard says what was not sent, so nothing is silently lost.
        self.booking_timezone: str = _str("BOOKING_TIMEZONE", "Asia/Kolkata")
        self.booking_duration_minutes: int = _int("BOOKING_DURATION_MINUTES", 30)
        self.company_name: str = _str("COMPANY_NAME", "our team")

        # Counsellor working hours on the 24 hour clock, and working days as
        # ISO weekday numbers (1 Monday .. 7 Sunday). The Appointments page
        # offers slots of BOOKING_DURATION_MINUTES inside these. Keep them in
        # step with COUNSELLOR_WORK_START/END in agent/.env, which Maya uses
        # to read "six" as 6 pm.
        self.counsellor_work_start: int = _int("COUNSELLOR_WORK_START", 10)
        self.counsellor_work_end: int = _int("COUNSELLOR_WORK_END", 19)
        self.counsellor_work_days: list[int] = [
            int(d) for d in _csv("COUNSELLOR_WORK_DAYS", "1,2,3,4,5,6") if d.isdigit()
        ] or [1, 2, 3, 4, 5, 6]

        # zoom | google | none. The DEFAULT platform: used when the lead has
        # no preference ("anything is fine"). Any other platform whose
        # credentials are filled in below is also available, and Maya offers
        # the lead the choice between the configured ones on the call.
        self.meeting_provider: str = _str("MEETING_PROVIDER", "none").lower()
        # Zoom Server-to-Server OAuth app (marketplace.zoom.us -> Develop ->
        # Build App -> Server-to-Server OAuth). Scope: meeting:write:admin.
        self.zoom_account_id: str = _str("ZOOM_ACCOUNT_ID")
        self.zoom_client_id: str = _str("ZOOM_CLIENT_ID")
        self.zoom_client_secret: str = _str("ZOOM_CLIENT_SECRET")
        self.zoom_host_user: str = _str("ZOOM_HOST_USER", "me")
        # Google Calendar with Meet. OAuth client + a one-time refresh token
        # for the counsellor's Google account (docs/BOOKINGS.md).
        self.google_client_id: str = _str("GOOGLE_CLIENT_ID")
        self.google_client_secret: str = _str("GOOGLE_CLIENT_SECRET")
        self.google_refresh_token: str = _str("GOOGLE_REFRESH_TOKEN")
        self.google_calendar_id: str = _str("GOOGLE_CALENDAR_ID", "primary")

        # meta | none. Meta's WhatsApp Cloud API: a business-initiated message
        # must be an approved template, so the template name is config.
        self.whatsapp_provider: str = _str("WHATSAPP_PROVIDER", "none").lower()
        self.whatsapp_phone_number_id: str = _str("WHATSAPP_PHONE_NUMBER_ID")
        self.whatsapp_access_token: str = _str("WHATSAPP_ACCESS_TOKEN")
        self.whatsapp_template_name: str = _str("WHATSAPP_TEMPLATE_NAME", "booking_confirmation")
        self.whatsapp_template_language: str = _str("WHATSAPP_TEMPLATE_LANGUAGE", "en")

        # --- Dashboard sign in ---------------------------------------------
        # Dashboard users sign in with Supabase Auth; the backend verifies
        # their token against Supabase's public signing key (app/auth.py).
        # Only projects that still sign with the legacy shared secret need
        # SUPABASE_JWT_SECRET; leave it blank otherwise.
        self.supabase_jwt_secret: str = _str("SUPABASE_JWT_SECRET")
        # Where invitation and password reset links should land. Defaults to
        # the first CORS origin, which is the dashboard's own address.
        self.frontend_base_url: str = _str("FRONTEND_BASE_URL", self.cors_origins[0] if self.cors_origins else "http://localhost:3000").rstrip("/")

        # --- Compliance -----------------------------------------------------
        # When on, a number on the do-not-call list is never dialled unless the
        # lead has a recorded consent timestamp inside the window below.
        self.dnd_check_enabled: bool = _bool("DND_CHECK_ENABLED", True)
        self.consent_window_days: int = _int("CONSENT_WINDOW_DAYS", 7)

        # --- Brakes on the public form (see throttle.py) ----------------------
        # Submissions per client address per rolling hour, and the minimum gap
        # between two calls to the same number. 0 turns either one off.
        self.lead_max_per_ip_per_hour: int = _int("LEAD_MAX_PER_IP_PER_HOUR", 5)
        self.lead_phone_cooldown_minutes: int = _int("LEAD_PHONE_COOLDOWN_MINUTES", 60)

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
                if not self.livekit_sip_trunk_id:
                    missing.append("LIVEKIT_SIP_TRUNK_ID")

        # A provider that is switched on must be complete. "none" needs nothing.
        if self.meeting_provider == "zoom":
            for name in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"):
                if not getattr(self, name.lower()):
                    missing.append(name)
        elif self.meeting_provider == "google":
            for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"):
                if not getattr(self, name.lower()):
                    missing.append(name)
        elif self.meeting_provider != "none":
            missing.append(f"MEETING_PROVIDER is '{self.meeting_provider}', must be zoom, google or none")

        if self.whatsapp_provider == "meta":
            for name in ("WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN"):
                if not getattr(self, name.lower()):
                    missing.append(name)
        elif self.whatsapp_provider != "none":
            missing.append(f"WHATSAPP_PROVIDER is '{self.whatsapp_provider}', must be meta or none")

        return missing

    def zoom_configured(self) -> bool:
        return bool(self.zoom_account_id and self.zoom_client_id and self.zoom_client_secret)

    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.google_refresh_token)

    def meeting_platforms(self) -> list[str]:
        """
        Platforms a lead may choose from, default first. A platform counts
        when its credentials are present, whether or not it is the default,
        so filling in both Zoom and Google gives the lead the choice.
        """
        out: list[str] = []
        if self.meeting_provider in ("zoom", "google"):
            out.append(self.meeting_provider)
        if self.zoom_configured() and "zoom" not in out:
            out.append("zoom")
        if self.google_configured() and "google" not in out:
            out.append("google")
        return out

    def describe_bookings(self) -> str:
        platforms = self.meeting_platforms()
        meeting = (
            f"meeting links via {', '.join(platforms)} (default {platforms[0]})"
            if platforms
            else "no meeting links (MEETING_PROVIDER=none)"
        )
        whatsapp = (
            f"WhatsApp via {self.whatsapp_provider} template '{self.whatsapp_template_name}'"
            if self.whatsapp_provider != "none"
            else "no WhatsApp (WHATSAPP_PROVIDER=none)"
        )
        return f"{meeting}; {whatsapp}"

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
        return "call status read from LiveKit, no webhooks needed"


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
