"""
Agent configuration.

Every environment value lands here and is validated at import time, so a
missing key is a clear message at startup rather than a failure twenty seconds
into a live call with a real lead on the line.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# src/config.py -> src/ -> agent/
AGENT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = AGENT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_TRUTHY = {"1", "true", "yes", "on"}


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _bool(name: str, default: bool) -> bool:
    raw = _str(name)
    return default if raw == "" else raw.lower() in _TRUTHY


def _int(name: str, default: int) -> int:
    try:
        return int(_str(name))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_str(name))
    except ValueError:
        return default


class Config:
    def __init__(self) -> None:
        # --- LiveKit: the room -------------------------------------------
        self.livekit_url = _str("LIVEKIT_URL")
        self.livekit_api_key = _str("LIVEKIT_API_KEY")
        self.livekit_api_secret = _str("LIVEKIT_API_SECRET")

        # --- Backend: where lead context and transcripts live -------------
        self.backend_base_url = _str("BACKEND_BASE_URL", "http://localhost:8000/api").rstrip("/")
        self.agent_api_key = _str("AGENT_API_KEY")

        # --- Sarvam: ears, brain and voice --------------------------------
        # One key covers all three layers.
        self.sarvam_api_key = _str("SARVAM_API_KEY")

        # Speech to text. 'codemix' is the mode built for Hindi and English in
        # the same sentence, which is how Indian admissions calls actually
        # sound. Use language='auto' if callers may open in either language.
        self.stt_language = _str("SARVAM_STT_LANGUAGE", "hi-IN")
        self.stt_mode = _str("SARVAM_STT_MODE", "codemix")
        self.stt_stream_type = _str("SARVAM_STT_STREAM_TYPE", "fast")

        # --- The brain -------------------------------------------------------
        #
        # Sarvam's chat completions API is in a closed beta. A normal Sarvam
        # account gets HTTP 400 "This endpoint is currently in beta and not
        # available" on every request, which is exactly what happened on the
        # first real call: ears and voice worked, the brain was refused, and
        # the agent sat in the room in silence.
        #
        # So the brain is a separate, switchable choice:
        #
        #   openai   default. Uses livekit-plugins-openai, already installed as
        #            a dependency. Needs OPENAI_API_KEY.
        #   groq     same plugin, Groq's endpoint. Very fast, cheap, good for
        #            short phone turns. Needs GROQ_API_KEY.
        #   sarvam   the original. Only works once Sarvam grants beta access.
        #            Needs nothing extra, SARVAM_API_KEY covers it.
        #
        # Ears (STT) and voice (TTS) stay on Sarvam regardless. Those endpoints
        # are generally available and proven working on this account.
        self.llm_provider = _str("LLM_PROVIDER", "openai").lower()
        self.openai_api_key = _str("OPENAI_API_KEY")
        self.openai_model = _str("OPENAI_MODEL", "gpt-4o-mini")
        self.groq_api_key = _str("GROQ_API_KEY")
        # Groq retired every Llama model on 16 Aug 2026 (their deprecations
        # page). Both llama-3.3-70b-versatile and llama-3.1-8b-instant now
        # return 404 "does not exist or you do not have access". The named
        # replacements are openai/gpt-oss-120b and openai/gpt-oss-20b. The
        # 120b is stronger at Hindi and still fast on Groq; use the 20b if
        # you want the absolute lowest latency.
        self.groq_model = _str("GROQ_MODEL", "openai/gpt-oss-120b")
        self.llm_model = _str("SARVAM_LLM_MODEL", "sarvam-105b")

        # The voice. This is the largest single cost in a call, about two
        # thirds of the Sarvam bill, which is why the prompt keeps replies to
        # one or two sentences.
        self.tts_model = _str("SARVAM_TTS_MODEL", "bulbul:v3")
        self.tts_language = _str("SARVAM_TTS_LANGUAGE", "hi-IN")
        # Speaker names are tied to the TTS model version. 'anushka' belongs to
        # bulbul:v2 and was removed in v3, which the plugin rejects outright at
        # construction time, crashing the job before the agent can speak.
        #
        # Valid speakers for bulbul:v3, as the installed plugin reports them:
        #   shubh, ritu, rahul, pooja, simran, kavya, amit, ratan, rohan, dev,
        #   ishita, shreya, manan, sumit, priya, aditya, kabir, neha, varun,
        #   roopa, aayan, ashutosh, advait, amelia, sophia, suhani, rupali,
        #   tanya, shruti, kavitha
        self.tts_speaker = _str("SARVAM_TTS_SPEAKER", "priya")
        self.tts_pace = _float("SARVAM_TTS_PACE", 1.0)

        # --- Behaviour -----------------------------------------------------
        self.agent_name = _str("AGENT_NAME", "Maya")
        self.agent_company = _str("AGENT_COMPANY", "our team")
        self.flush_interval_seconds = _int("AGENT_FLUSH_INTERVAL_SECONDS", 5)
        self.generate_summary = _bool("AGENT_GENERATE_SUMMARY", True)

        # Room names the agent will act on. Anything else it leaves alone, so
        # a stray room in the same LiveKit project cannot confuse it.
        self.room_prefix = _str("AGENT_ROOM_PREFIX", "call-")

    def missing(self) -> list[str]:
        gaps = []
        if not self.livekit_url:
            gaps.append("LIVEKIT_URL")
        if not self.livekit_api_key:
            gaps.append("LIVEKIT_API_KEY")
        if not self.livekit_api_secret:
            gaps.append("LIVEKIT_API_SECRET")
        if not self.agent_api_key:
            gaps.append("AGENT_API_KEY")
        if not self.sarvam_api_key:
            gaps.append("SARVAM_API_KEY")

        # The brain needs its own key unless it is Sarvam's.
        if self.llm_provider == "openai" and not self.openai_api_key:
            gaps.append("OPENAI_API_KEY (or set LLM_PROVIDER=groq / sarvam)")
        elif self.llm_provider == "groq" and not self.groq_api_key:
            gaps.append("GROQ_API_KEY (or set LLM_PROVIDER=openai / sarvam)")
        elif self.llm_provider not in ("openai", "groq", "sarvam"):
            gaps.append(f"LLM_PROVIDER is '{self.llm_provider}', must be openai, groq or sarvam")
        return gaps

    def llm_label(self) -> str:
        if self.llm_provider == "sarvam":
            return f"sarvam:{self.llm_model}"
        if self.llm_provider == "groq":
            return f"groq:{self.groq_model}"
        return f"openai:{self.openai_model}"

    def describe(self) -> str:
        return (
            f"stt=sarvam:{self.stt_mode}/{self.stt_language} "
            f"llm={self.llm_label()} "
            f"tts=sarvam:{self.tts_model}/{self.tts_speaker}"
        )


config = Config()

# `download-files` only fetches model weights; it needs no keys and runs at
# Docker build time where no .env exists. Every other subcommand (dev, start)
# must fail loudly here rather than twenty seconds into a live call.
_gaps = [] if "download-files" in sys.argv else config.missing()
if _gaps:
    print("\nThe agent cannot start. Missing in agent/.env:\n", file=sys.stderr)
    for _name in _gaps:
        print(f"  - {_name}", file=sys.stderr)
    print(f"\nFile checked: {ENV_PATH}", file=sys.stderr)
    print("Copy agent/.env.example to agent/.env and fill it in.\n", file=sys.stderr)
    raise SystemExit(1)
