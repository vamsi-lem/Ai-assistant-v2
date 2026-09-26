"""
Agent self-check, version 2.

Version 1 confirmed the Sarvam classes exist. What it could not tell us is
whether the VALUES this project passes them are accepted. Sarvam constrains
several of those arguments to fixed lists (RealtimeMode, SarvamLLMModels,
SarvamTTSSpeakers and so on), and a value outside the list is rejected at call
time rather than at startup. The agent then sits in the room saying nothing,
which looks identical to a dozen other faults.

So this version reads the allowed values straight out of the installed package
and checks the project's settings against them. No guessing from docs.

Run it from the agent folder, with the project's own Python (the system
Python does not have the packages and fails on the first import):

    cd agent
    .venv\\Scripts\\python.exe check_agent.py
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import pkgutil
import sys
import typing
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

LINE = "-" * 74


def head(title: str) -> None:
    print(f"\n{title}")
    print(LINE)


# ---------------------------------------------------------------------------
# 1. Versions
# ---------------------------------------------------------------------------


def check_versions() -> None:
    head("1. Installed versions")
    from importlib.metadata import version

    for package in (
        "livekit-agents",
        "livekit-plugins-sarvam",
        "livekit-plugins-silero",
        "livekit-plugins-turn-detector",
    ):
        try:
            print(f"  {package:<32} {version(package)}")
        except Exception:  # noqa: BLE001
            print(f"  {package:<32} not installed")


# ---------------------------------------------------------------------------
# 2. The allowed values, read from the package itself
# ---------------------------------------------------------------------------


def collect_literals() -> dict[str, tuple]:
    """
    Walk the Sarvam plugin and collect every Literal type alias it defines.

    These aliases ARE the allowed-value lists. Reading them here means the
    answer comes from the version actually installed on this machine, rather
    than from documentation that may describe a different release.
    """
    found: dict[str, tuple] = {}

    try:
        import livekit.plugins.sarvam as root
    except Exception as exc:  # noqa: BLE001
        print(f"  cannot import the Sarvam plugin: {exc}")
        return found

    modules = [root]
    package_path = getattr(root, "__path__", None)
    if package_path:
        for info in pkgutil.iter_modules(package_path):
            try:
                modules.append(importlib.import_module(f"{root.__name__}.{info.name}"))
            except Exception:  # noqa: BLE001 - a module that will not import is not fatal here
                pass

    for module in modules:
        for name, value in vars(module).items():
            if name.startswith("_"):
                continue
            if typing.get_origin(value) is typing.Literal:
                args = typing.get_args(value)
                if name not in found:
                    found[name] = args

    return found


def check_allowed_values() -> dict[str, tuple]:
    head("2. Values Sarvam actually accepts (read from the installed package)")

    literals = collect_literals()
    if not literals:
        print("  No Literal type aliases found. The plugin may validate differently;")
        print("  in that case section 3 below is inconclusive and the agent log decides.")
        return literals

    for name in sorted(literals):
        values = literals[name]
        rendered = ", ".join(str(v) for v in values)
        if len(rendered) > 600:
            rendered = rendered[:600] + " ... (truncated)"
        print(f"\n  {name}")
        print(f"      {rendered}")

    return literals


# ---------------------------------------------------------------------------
# 3. This project's settings, checked against those lists
# ---------------------------------------------------------------------------


def check_project_settings(literals: dict[str, tuple]) -> None:
    head("3. What this project sends, and whether it is allowed")

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from src.config import config  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        print(f"  could not load src/config.py: {exc}")
        return

    # Each row: label, the value being sent, and the names of the Literal
    # aliases that could plausibly define its allowed set. Several names are
    # tried because the plugin is free to call them whatever it likes.
    rows = [
        ("STT language", config.stt_language, ("RealtimeLanguage", "SarvamSTTLanguages", "SarvamLanguages")),
        ("STT mode", config.stt_mode, ("RealtimeMode", "SarvamSTTModes")),
        ("STT stream_type", config.stt_stream_type, ("RealtimeStreamType",)),
        # No LLM row: the brain goes through the OpenAI client for every
        # provider, Sarvam included, so the Sarvam plugin's model list does
        # not apply to it.
        ("TTS model", config.tts_model, ("SarvamTTSModels",)),
        ("TTS language", config.tts_language, ("SarvamTTSLanguages", "SarvamLanguages")),
        ("TTS speaker", config.tts_speaker, ("SarvamTTSSpeakers",)),
    ]

    problems: list[str] = []

    for label, value, candidates in rows:
        alias = next((c for c in candidates if c in literals), None)

        if alias is None:
            print(f"  {label:<18} {value!r:<32} (no list found, cannot check)")
            continue

        allowed = literals[alias]
        if value in allowed:
            print(f"  {label:<18} {value!r:<32} OK  (in {alias})")
        else:
            print(f"  {label:<18} {value!r:<32} NOT ALLOWED  (per {alias})")
            sample = ", ".join(str(v) for v in allowed[:12])
            print(f"      allowed: {sample}{' ...' if len(allowed) > 12 else ''}")
            problems.append(f"{label} = {value!r} is not in {alias}")

    print()
    if problems:
        print("  ^^ THESE ARE THE PROBLEM. Each one makes Sarvam reject the request")
        print("     at call time, so the agent joins the room and then stays silent.")
        for problem in problems:
            print(f"       - {problem}")
    else:
        print("  Every value is in the allowed list. The silence is elsewhere;")
        print("  the agent window log will name it.")


# ---------------------------------------------------------------------------
# 4. Backend reachability
# ---------------------------------------------------------------------------


async def check_backend() -> None:
    head("4. Can the agent reach the backend")

    base = (os.environ.get("BACKEND_BASE_URL") or "http://127.0.0.1:8000/api").rstrip("/")

    # On Windows, 'localhost' resolves to IPv6 ::1 first. A server bound only to
    # IPv4 makes that attempt hang before falling back, which is why the first
    # run of this script appeared to freeze. 127.0.0.1 skips the question.
    candidates = [base]
    if "localhost" in base:
        candidates.append(base.replace("localhost", "127.0.0.1"))

    import aiohttp

    for candidate in candidates:
        url = f"{candidate}/health"
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.get(url) as response:
                    body = await response.text()
                    print(f"  GET {url}")
                    print(f"  HTTP {response.status}  {body[:300]}")
                    if "localhost" in base and candidate != base:
                        print()
                        print("  NOTE: localhost failed but 127.0.0.1 worked. Change")
                        print("  BACKEND_BASE_URL in agent/.env to use 127.0.0.1 and")
                        print("  restart. This matters: the agent asks the backend for")
                        print("  the lead's name BEFORE it speaks, and gives up quietly")
                        print("  if that call fails.")
                    return
        except Exception as exc:  # noqa: BLE001
            print(f"  GET {url} failed: {type(exc).__name__}: {exc}")

    print()
    print("  The agent cannot reach the backend. It fetches the lead's name before")
    print("  saying hello, and leaves the room without speaking if that fails.")
    print("  Make sure the BACKEND window is running, then try again.")


# ---------------------------------------------------------------------------
# 5. Framework API used by src/main.py
# ---------------------------------------------------------------------------


def check_framework_api() -> None:
    """
    Every name below is something src/main.py calls. If one prints MISSING,
    the agent will crash at that point on the first call. Better to know now.
    """
    head("5. Framework API used by the agent (must all be OK)")

    def report(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {label:<52} {'OK' if ok else 'MISSING'}  {detail}")

    try:
        import livekit.agents as agents

        for name in ("RoomInputOptions", "RunContext", "StopResponse", "function_tool", "get_job_context"):
            report(f"livekit.agents.{name}", hasattr(agents, name))

        params = inspect.signature(agents.AgentSession.__init__).parameters
        for name in (
            "min_endpointing_delay",
            "max_endpointing_delay",
            "min_interruption_duration",
            "preemptive_generation",
        ):
            report(f"AgentSession(... {name}=)", name in params)
        # These three are what stop background talk cutting Maya off. The
        # agent skips any that are missing and logs it; older versions lack
        # them, in which case upgrade livekit-agents.
        for name in ("min_interruption_words", "false_interruption_timeout", "resume_false_interruption"):
            report(f"AgentSession(... {name}=)", name in params, "" if name in params else "upgrade livekit-agents")

        report("RunContext.wait_for_playout", hasattr(agents.RunContext, "wait_for_playout"))

        # Token budget on Groq's free tier: the agent sends only the last few
        # transcript lines each turn and waits longer on a 429. Both have a
        # fallback if missing, so MISSING here is a note, not a failure.
        from livekit.agents.llm import ChatContext

        report("ChatContext.truncate (history trimming)", hasattr(ChatContext, "truncate"), "" if hasattr(ChatContext, "truncate") else "manual trim used")
        report("AgentSession(... conn_options=) (429 retries)", "conn_options" in params, "" if "conn_options" in params else "framework default retries")
        try:
            from livekit.agents import APIConnectOptions  # noqa: F401
            from livekit.agents.voice import SessionConnectOptions  # noqa: F401

            report("SessionConnectOptions / APIConnectOptions", True)
        except Exception:  # noqa: BLE001
            report("SessionConnectOptions / APIConnectOptions", False, "framework default retries")

        from livekit import api as lk_api

        report("livekit.api.DeleteRoomRequest", hasattr(lk_api, "DeleteRoomRequest"))

        start_params = inspect.signature(agents.AgentSession.start).parameters
        report("AgentSession.start(room_input_options=)", "room_input_options" in start_params)

        reply_params = inspect.signature(agents.AgentSession.generate_reply).parameters
        report("AgentSession.generate_reply(allow_interruptions=)", "allow_interruptions" in reply_params)

        report("AgentSession.agent_state", hasattr(agents.AgentSession, "agent_state"))
        report("AgentSession.say", hasattr(agents.AgentSession, "say"))
        report("Agent.on_user_turn_completed", hasattr(agents.Agent, "on_user_turn_completed"))
        report("Agent.update_instructions", hasattr(agents.Agent, "update_instructions"))
        report("Agent.session", isinstance(getattr(agents.Agent, "session", None), property))
        # The voice filter in src/main.py wraps the default TTS step.
        default = getattr(agents.Agent, "default", None)
        report("Agent.default.tts_node", default is not None and hasattr(default, "tts_node"))
        report("JobContext.shutdown", hasattr(agents.JobContext, "shutdown"))

        from livekit.agents.voice import SpeechHandle  # type: ignore[import-not-found]

        report("SpeechHandle.wait_for_playout", hasattr(SpeechHandle, "wait_for_playout"))
    except Exception as exc:  # noqa: BLE001
        print(f"  could not inspect livekit.agents: {exc}")

    try:
        from livekit.plugins import sarvam

        report("sarvam.TTS.update_options", hasattr(sarvam.TTS, "update_options"))
        report("sarvam.STTRealtime.update_options", hasattr(sarvam.STTRealtime, "update_options"))
        if hasattr(sarvam.TTS, "update_options"):
            print(f"      TTS.update_options{inspect.signature(sarvam.TTS.update_options)}")
        if hasattr(sarvam.STTRealtime, "update_options"):
            print(f"      STTRealtime.update_options{inspect.signature(sarvam.STTRealtime.update_options)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  could not inspect the Sarvam plugin: {exc}")

    try:
        from livekit.plugins import noise_cancellation

        report("livekit.plugins.noise_cancellation.BVC", hasattr(noise_cancellation, "BVC"))
    except ImportError:
        report("livekit.plugins.noise_cancellation", False, "run setup.ps1 again to install it")


async def main() -> int:
    print("\nAgent self-check v2")
    print("=" * 74)
    check_versions()
    literals = check_allowed_values()
    check_project_settings(literals)
    check_framework_api()
    await check_backend()
    print("\nDone. Paste all of the above.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
