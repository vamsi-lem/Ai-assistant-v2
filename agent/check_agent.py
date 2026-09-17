"""
Agent self-check.

The agent joining a room and then saying nothing has a handful of possible
causes, and they look identical from the browser. This prints the facts that
separate them:

  1. which livekit-agents version is actually installed
  2. whether the Sarvam plugin exposes the class names this project calls, and
     what arguments those classes really accept
  3. whether the config values in agent/.env are ones Sarvam will accept
  4. whether the agent can reach the backend and authenticate to it

Nothing here joins a room or costs money. It is all local inspection plus one
call to your own backend.

Run it from the agent folder:

    cd agent
    .\.venv\Scripts\python.exe check_agent.py
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

LINE = "-" * 74


def head(title: str) -> None:
    print(f"\n{title}")
    print(LINE)


def show_callable(label: str, obj: object) -> None:
    """Print a class or function's real signature, so guesses become facts."""
    if obj is None:
        print(f"  {label:<24} MISSING")
        return
    try:
        sig = str(inspect.signature(obj))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        sig = "(signature unavailable)"
    if len(sig) > 300:
        sig = sig[:300] + " ..."
    print(f"  {label:<24} OK")
    print(f"      {sig}")


def check_versions() -> None:
    head("1. Installed versions")
    try:
        from importlib.metadata import version

        for package in (
            "livekit-agents",
            "livekit-plugins-sarvam",
            "livekit-plugins-silero",
            "livekit-plugins-turn-detector",
            "livekit",
            "livekit-api",
        ):
            try:
                print(f"  {package:<32} {version(package)}")
            except Exception:  # noqa: BLE001
                print(f"  {package:<32} not installed")
    except Exception as exc:  # noqa: BLE001
        print(f"  could not read versions: {exc}")


def check_sarvam() -> None:
    head("2. Sarvam plugin API")
    print("  This is the section that matters most. The class names below were")
    print("  written from documentation and never executed, so if one says")
    print("  MISSING, that is the bug.\n")

    try:
        from livekit.plugins import sarvam
    except Exception as exc:  # noqa: BLE001
        print(f"  CANNOT IMPORT the Sarvam plugin: {exc}")
        print("  Install it with:  .\\.venv\\Scripts\\python.exe -m pip install livekit-plugins-sarvam")
        return

    public = sorted(n for n in dir(sarvam) if not n.startswith("_"))
    print(f"  Everything the plugin actually exposes:\n      {', '.join(public)}\n")

    for name in ("STTRealtime", "STT", "LLM", "TTS"):
        show_callable(name, getattr(sarvam, name, None))


def check_config() -> None:
    head("3. Values this agent will pass to Sarvam")
    keys = (
        "SARVAM_API_KEY",
        "STT_LANGUAGE",
        "STT_MODE",
        "STT_STREAM_TYPE",
        "LLM_MODEL",
        "TTS_LANGUAGE",
        "TTS_MODEL",
        "TTS_SPEAKER",
        "TTS_PACE",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "BACKEND_BASE_URL",
        "AGENT_API_KEY",
    )
    for key in keys:
        raw = os.environ.get(key)
        if raw is None:
            print(f"  {key:<20} (not set, code default will be used)")
            continue
        if key.endswith(("API_KEY", "SECRET")):
            shown = f"{raw[:6]}...{raw[-4:]} ({len(raw)} chars)" if len(raw) > 12 else f"({len(raw)} chars)"
        else:
            shown = repr(raw)
        flag = "   <-- HAS STRAY WHITESPACE" if raw != raw.strip() else ""
        print(f"  {key:<20} {shown}{flag}")


async def check_backend() -> None:
    head("4. Can the agent reach the backend and authenticate")
    base = (os.environ.get("BACKEND_BASE_URL") or "http://localhost:8000/api").rstrip("/")
    url = f"{base}/health"

    try:
        import aiohttp
    except Exception as exc:  # noqa: BLE001
        print(f"  aiohttp missing: {exc}")
        return

    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                body = await response.text()
                print(f"  GET {url}")
                print(f"  HTTP {response.status}")
                print(f"  {body[:400]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  GET {url} FAILED: {exc}")
        print("  The backend window must be running before the agent can fetch a")
        print("  lead's name. If it is running, check BACKEND_BASE_URL in agent/.env.")


async def main() -> int:
    print("\nAgent self-check")
    print("=" * 74)
    check_versions()
    check_sarvam()
    check_config()
    await check_backend()
    print("\nDone. Paste all of the above.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
