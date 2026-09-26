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
        # The brain is a separate, switchable choice from the ears and voice.
        # All four go through livekit-plugins-openai, since all four speak the
        # OpenAI wire protocol; only the URL, key and model differ.
        #
        #   openai   default. Needs OPENAI_API_KEY.
        #   groq     Groq's endpoint. Very fast, cheap, good for short phone
        #            turns. Needs GROQ_API_KEY. Free tier is 8,000 tokens a
        #            minute, too little for a real call.
        #   gemini   Google's OpenAI compatible endpoint. The free tier needs
        #            no card and allows about 250,000 tokens a minute, so it
        #            is the right free brain for testing. Needs GEMINI_API_KEY
        #            from aistudio.google.com.
        #   sarvam   Sarvam's v1 chat completions endpoint, which is generally
        #            available (their v2 endpoint is still whitelisted per
        #            key, so we do not use it). Needs nothing extra,
        #            SARVAM_API_KEY covers it. The first call on this project
        #            hit a 400 "currently in beta" from the plugin's own LLM
        #            class, which is why the agent now talks to Sarvam through
        #            the OpenAI client instead.
        #
        # Ears (STT) and voice (TTS) stay on Sarvam regardless. Those endpoints
        # are generally available and proven working on this account.
        self.llm_provider = _str("LLM_PROVIDER", "openai").lower()
        self.openai_api_key = _str("OPENAI_API_KEY")
        self.openai_model = _str("OPENAI_MODEL", "gpt-4o-mini")
        self.gemini_api_key = _str("GEMINI_API_KEY")
        # Free tier per minute: flash-lite allows 30 requests, flash 10. A
        # phone turn is one request, so flash-lite is the safe default; a
        # fast talker can make more than 10 turns in a minute.
        self.gemini_model = _str("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.groq_api_key = _str("GROQ_API_KEY")
        # Groq retired every Llama model on 16 Aug 2026 (their deprecations
        # page). Both llama-3.3-70b-versatile and llama-3.1-8b-instant now
        # return 404 "does not exist or you do not have access". The named
        # replacements are openai/gpt-oss-120b and openai/gpt-oss-20b. The
        # 120b is stronger at Hindi and still fast on Groq; use the 20b if
        # you want the absolute lowest latency.
        self.groq_model = _str("GROQ_MODEL", "openai/gpt-oss-120b")
        # sarvam-105b-conversations is the variant Sarvam documents for
        # "real-time conversational and voice-agent workloads" (32K context,
        # plenty for a trimmed call). sarvam-105b is the general 128K model.
        self.llm_model = _str("SARVAM_LLM_MODEL", "sarvam-105b-conversations")

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
        # How expressive the voice is. Sarvam's own guide: 0.3 to 0.5 is a
        # flat professional read, 0.6 is reliable, 0.7 to 0.8 is warm and
        # conversational, above 0.9 is theatrical. A counsellor on the phone
        # is warm, so 0.75.
        self.tts_temperature = _float("SARVAM_TTS_TEMPERATURE", 0.75)

        # --- Languages ---------------------------------------------------------
        #
        # Maya greets in AGENT_GREETING_LANGUAGE, asks which of AGENT_LANGUAGES
        # the lead wants, then switches ears and voice to their answer for the
        # rest of the call. Names are English, lowercase, comma separated, and
        # must be ones Sarvam speaks (see LANGUAGES in prompts.py).
        self.offered_languages = [
            x.strip().lower()
            for x in _str("AGENT_LANGUAGES", "english,hindi,telugu").split(",")
            if x.strip()
        ]
        self.greeting_language = _str("AGENT_GREETING_LANGUAGE", "en-IN")

        # --- Turn timing -----------------------------------------------------
        #
        # How long Maya waits after the lead stops talking before she replies,
        # and how much speech counts as a real interruption. The framework
        # defaults are conservative and feel slow on a phone. These are
        # tighter without being twitchy; tune in .env if she cuts people off
        # or waits too long.
        self.min_endpointing_delay = _float("AGENT_MIN_ENDPOINTING_DELAY", 0.6)
        self.max_endpointing_delay = _float("AGENT_MAX_ENDPOINTING_DELAY", 3.0)

        # How the end of the lead's turn is decided.
        #   vad    silence alone: after min_endpointing_delay of quiet, the
        #          turn is over. Fastest, nothing to wait for. The default.
        #   stt    the ears' own end-of-sentence signal plus the delays above.
        #   auto   the framework's turn-detector model. On a real call it
        #          was timing out against LiveKit's cloud ("eot prediction
        #          timed out") and adding two to four seconds per reply.
        mode = _str("AGENT_TURN_DETECTION", "vad").lower()
        self.turn_detection = mode if mode in ("vad", "stt", "auto") else "vad"

        # --- Interruptions ------------------------------------------------------
        #
        # The Telugu test call: every one of Maya's replies was cut mid
        # sentence by background talk, because 0.7 seconds of any speech
        # counted as the lead talking over her. Production agents demand more
        # before they stop: a real interruption is a second or more of speech
        # AND several words of transcript. A cough, a "hmm", or a TV in the
        # next room is neither. If she does stop and no words arrive within
        # the false-interruption window, she picks up where she left off.
        self.min_interruption_duration = _float("AGENT_MIN_INTERRUPTION_DURATION", 1.2)
        self.min_interruption_words = _int("AGENT_MIN_INTERRUPTION_WORDS", 3)
        self.false_interruption_timeout = _float("AGENT_FALSE_INTERRUPTION_TIMEOUT", 2.0)
        self.resume_false_interruption = _bool("AGENT_RESUME_FALSE_INTERRUPTION", True)

        # --- Silence handling -------------------------------------------------
        #
        # After this many seconds of silence Maya asks if the lead is still
        # there; after that many more she says goodbye and ends the call.
        self.idle_prompt_seconds = _int("AGENT_IDLE_PROMPT_SECONDS", 12)
        self.idle_hangup_seconds = _int("AGENT_IDLE_HANGUP_SECONDS", 15)

        # --- Phone calls ----------------------------------------------------------
        #
        # On the phone path the room exists while the lead's mobile is still
        # ringing. Maya waits this long for them to pick up before recording
        # the call as no-answer. Keep it a little above the carrier's own
        # ringing timeout (40s in the backend) so the carrier decides first.
        self.answer_timeout_seconds = _int("AGENT_ANSWER_TIMEOUT_SECONDS", 45)

        # --- Noise handling -----------------------------------------------------
        #
        # Turns Maya could not use, in a row (background talk, garbled audio,
        # wrong script), before she gives up gracefully: says a counsellor
        # will call at a better time, and ends the call. The second such turn
        # already gets a "did not catch that"; this is the ceiling.
        self.unclear_turns_before_close = _int("AGENT_UNCLEAR_TURNS_BEFORE_CLOSE", 4)

        # --- Token budget -------------------------------------------------------
        #
        # Every reply sends the brain the instructions, the tools and the
        # conversation so far. On Groq's free tier (8,000 tokens a minute) a
        # long transcript is what trips the limit and makes Maya lose turns.
        # Only the last this many conversation items (a lead line or a Maya
        # line each count as one) are sent per reply; the full transcript is
        # still stored. 0 sends everything. 12 is six exchanges, enough to
        # hold the current stage of the script.
        self.history_items = _int("AGENT_HISTORY_ITEMS", 12)

        # When the brain answers 429 (rate limited), how many times to retry
        # and how long to wait between tries. Groq says "try again in 6s" on
        # its free tier, so the default waits long enough to get through
        # rather than dropping the turn. On a paid brain these rarely matter.
        self.llm_max_retries = _int("AGENT_LLM_MAX_RETRIES", 5)
        self.llm_retry_interval = _float("AGENT_LLM_RETRY_INTERVAL", 3.0)

        # --- Behaviour -----------------------------------------------------
        self.agent_name = _str("AGENT_NAME", "Maya")
        # For working out "tomorrow at six" and for telling the lead when
        # counsellors are available. Plain words, read aloud.
        self.booking_timezone = _str("BOOKING_TIMEZONE", "Asia/Kolkata")
        self.counsellor_hours = _str("COUNSELLOR_HOURS", "Monday to Saturday, ten in the morning to seven in the evening")
        # The same hours as numbers (24 hour clock), used by the code that
        # turns "six" into 6 pm rather than 6 am. Keep in step with the
        # sentence above.
        self.work_start_hour = _int("COUNSELLOR_WORK_START", 10)
        self.work_end_hour = _int("COUNSELLOR_WORK_END", 19)
        self.agent_company = _str("AGENT_COMPANY", "our team")

        # Which conversation Maya runs:
        #   short  greet, language, ask for a day and time, book, goodbye.
        #          Nothing else. Cheapest on tokens, quickest to test the
        #          booking, Zoom and WhatsApp chain end to end.
        #   full   the six stage script: identity, interest, offer the
        #          session, exact slot with read back, book, close.
        flow = _str("AGENT_FLOW", "short").lower()
        self.flow = flow if flow in ("short", "full") else "short"

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
            gaps.append("OPENAI_API_KEY (or set LLM_PROVIDER=gemini / groq / sarvam)")
        elif self.llm_provider == "gemini" and not self.gemini_api_key:
            gaps.append("GEMINI_API_KEY (or set LLM_PROVIDER=openai / groq / sarvam)")
        elif self.llm_provider == "groq" and not self.groq_api_key:
            gaps.append("GROQ_API_KEY (or set LLM_PROVIDER=gemini / openai / sarvam)")
        elif self.llm_provider not in ("openai", "gemini", "groq", "sarvam"):
            gaps.append(f"LLM_PROVIDER is '{self.llm_provider}', must be openai, gemini, groq or sarvam")
        return gaps

    def llm_label(self) -> str:
        if self.llm_provider == "sarvam":
            return f"sarvam:{self.llm_model}"
        if self.llm_provider == "gemini":
            return f"gemini:{self.gemini_model}"
        if self.llm_provider == "groq":
            return f"groq:{self.groq_model}"
        return f"openai:{self.openai_model}"

    def describe(self) -> str:
        return (
            f"flow={self.flow} languages={'/'.join(self.offered_languages)} greet={self.greeting_language} "
            f"stt=sarvam:{self.stt_mode}/{self.stt_language} "
            f"llm={self.llm_label()} "
            f"tts=sarvam:{self.tts_model}/{self.tts_speaker}@{self.tts_temperature}"
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
