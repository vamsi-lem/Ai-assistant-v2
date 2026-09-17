"""
AI Voice Platform v2 agent.

Joins the LiveKit room for one call, holds the conversation using Sarvam for
hearing, thinking and speaking, and stores the transcript through the backend.

Run locally:
    python -m src.main dev

Run in production (Railway):
    python -m src.main start

Who does what, because this confuses everyone:
    LiveKit   the room that carries audio. Not the agent.
    Sarvam    the ears and the voice. Not the agent.
    LLM       the brain. OpenAI by default, Groq or Sarvam by config.
    THIS FILE the agent.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    cli,
)
from livekit.agents.llm import ChatMessage
from livekit.plugins import sarvam, silero

from .backend_client import BackendClient, call_id_from_room
from .config import config
from .prompts import SUMMARY_PROMPT, build_greeting, build_instructions

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# agent/src/main.py -> agent/src -> agent/agent.log
LOG_PATH = Path(__file__).resolve().parent.parent / "agent.log"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
logger = logging.getLogger("agent")


def attach_file_log() -> None:
    """
    Mirror everything to agent/agent.log as well as the console.

    Two reasons this is worth the few lines. The console window scrolls, and a
    crash that matters is usually several hundred lines above where you are
    looking. And piping the output to a file from PowerShell changes how the
    LiveKit CLI behaves, which cost us a debugging round already.

    Called again from the worker setup and from each job, because LiveKit's CLI
    reconfigures logging after import and each job runs in its own process.
    Guarded so it never attaches twice.
    """
    root = logging.getLogger()
    if any(isinstance(h, logging.FileHandler) for h in root.handlers):
        return
    try:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    except OSError:  # a read-only deploy target must not stop the agent
        return
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    root.addHandler(handler)


attach_file_log()

server = AgentServer()


# ---------------------------------------------------------------------------
# Per-process warmup
# ---------------------------------------------------------------------------


def prewarm(proc: JobProcess) -> None:
    """
    Load the voice activity detector once per worker process.

    VAD.load() is blocking and slow, so doing it per call would add that delay
    to the front of every conversation. setup_fnc is the current name for what
    used to be prewarm_fnc.
    """
    attach_file_log()
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD loaded. Voice stack: %s", config.describe())


server.setup_fnc = prewarm


# ---------------------------------------------------------------------------
# Transcript buffer
# ---------------------------------------------------------------------------


class Transcript:
    """
    Accumulates turns in memory and pushes the whole list to the backend.

    In-memory during the call so the hot path never waits on the network. The
    periodic flush and the shutdown hook do the writing.
    """

    def __init__(self, call_id: str, backend: BackendClient) -> None:
        self._call_id = call_id
        self._backend = backend
        self._turns: list[dict[str, Any]] = []
        self._dirty = False
        self._lock = asyncio.Lock()

    @property
    def turns(self) -> list[dict[str, Any]]:
        return list(self._turns)

    def add(self, role: str, text: str, interrupted: bool, at: float | None = None) -> None:
        moment = (
            datetime.fromtimestamp(at, tz=timezone.utc)
            if at
            else datetime.now(timezone.utc)
        )
        self._turns.append(
            {
                "role": role,
                "text": text,
                "at": moment.isoformat(),
                "interrupted": interrupted,
            }
        )
        self._dirty = True

    async def flush(
        self, *, summary: str | None = None, call_status: str | None = None
    ) -> None:
        """Serialised, so two flushes can never interleave and write out of order."""
        async with self._lock:
            if not self._dirty and summary is None and call_status is None:
                return
            await self._backend.store_conversation(
                call_id=self._call_id,
                messages=list(self._turns),
                summary=summary,
                call_status=call_status,
            )
            self._dirty = False


# ---------------------------------------------------------------------------
# The assistant
# ---------------------------------------------------------------------------


class Assistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)


def build_llm():
    """
    The brain, chosen by LLM_PROVIDER.

    Sarvam's chat API is in closed beta and refuses ordinary accounts with a
    400, so the default is OpenAI through livekit-plugins-openai, which is
    already installed. Groq uses the same plugin against Groq's endpoint.
    Sarvam stays available for when they grant access; switching back is one
    line in agent/.env and nothing else moves.

    Ears and voice are unaffected by this choice. They stay on Sarvam.
    """
    if config.llm_provider == "sarvam":
        return sarvam.LLM(model=config.llm_model)

    from livekit.plugins import openai as openai_plugin

    if config.llm_provider == "groq":
        # Groq speaks the OpenAI wire protocol, so the OpenAI plugin pointed at
        # Groq's URL is the whole integration. The plugin's old with_groq()
        # shortcut no longer exists in 1.8, which is what the first attempt
        # crashed on.
        return openai_plugin.LLM(
            model=config.groq_model,
            api_key=config.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    return openai_plugin.LLM(model=config.openai_model, api_key=config.openai_api_key)


async def generate_summary(session: AgentSession, turns: list[dict[str, Any]]) -> str | None:
    """
    Closing summary for the CRM record.

    Reuses the session's own Sarvam LLM rather than opening a second provider
    connection. Best effort: a failure here must never cost us the transcript,
    which is the thing that actually matters.
    """
    if not turns:
        return None

    transcript = "\n".join(
        f"{'Assistant' if t['role'] == 'assistant' else 'Lead'}: {t['text']}" for t in turns
    )

    try:
        # NOTE: I could not run this in the sandbox that wrote it. If the
        # session does not expose a one-shot chat call under this name in your
        # installed version, set AGENT_GENERATE_SUMMARY=false and tell me the
        # error. The transcript is stored either way; only the summary is lost.
        from livekit.agents import llm as llm_api

        chat_ctx = llm_api.ChatContext()
        chat_ctx.add_message(role="system", content=SUMMARY_PROMPT)
        chat_ctx.add_message(role="user", content=transcript)

        stream = session.llm.chat(chat_ctx=chat_ctx)
        chunks: list[str] = []
        async for chunk in stream:
            delta = getattr(getattr(chunk, "delta", None), "content", None)
            if delta:
                chunks.append(delta)

        text = "".join(chunks).strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate summary: %s", exc)
        return None


# ---------------------------------------------------------------------------
# One call
# ---------------------------------------------------------------------------


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    attach_file_log()

    # The room name is on the JOB, and it is readable immediately, before any
    # connect. This differs from the Node SDK, where it is empty until the room
    # is connected. Reading ctx.room.name here would give "" and the call would
    # be silently abandoned.
    room_name = ctx.job.room.name
    call_id = call_id_from_room(room_name)

    if not call_id:
        logger.warning(
            "Room %r is not a platform call room (expected %s<callId>). Leaving it alone.",
            room_name,
            config.room_prefix,
        )
        return

    ctx.log_context_fields = {"room": room_name, "call_id": call_id}
    backend = BackendClient()

    try:
        context = await backend.fetch_call_context(call_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not fetch context for call %s: %s", call_id, exc)
        logger.error(
            "Check BACKEND_BASE_URL is reachable (%s) and AGENT_API_KEY matches "
            "the backend.",
            config.backend_base_url,
        )
        await backend.close()
        return

    logger.info(
        "Call %s | lead %s | enquiry about %s | %s",
        call_id,
        context["name"],
        context["product_or_course"],
        config.describe(),
    )

    transcript = Transcript(call_id, backend)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        # Sarvam's realtime STT over websocket. 'codemix' keeps English words
        # as English inside a Hindi sentence, which is how these calls sound.
        stt=sarvam.STTRealtime(
            language=config.stt_language,
            mode=config.stt_mode,
            stream_type=config.stt_stream_type,
        ),
        llm=build_llm(),
        tts=sarvam.TTS(
            target_language_code=config.tts_language,
            model=config.tts_model,
            speaker=config.tts_speaker,
            pace=config.tts_pace,
        ),
    )

    # A plain def, NOT async def. AgentSession emits synchronously, so an async
    # handler here would create a coroutine nobody awaits and every turn would
    # be silently dropped.
    @session.on("conversation_item_added")
    def _on_item(event: ConversationItemAddedEvent) -> None:
        item = event.item
        if not isinstance(item, ChatMessage):
            return

        text = (item.text_content or "").strip()
        if not text:
            return

        role = "assistant" if item.role == "assistant" else "user"
        transcript.add(role, text, bool(item.interrupted), item.created_at)

    # Declared before finalize() so the shutdown hook can always reach it,
    # even if the session fails before the loop starts.
    flush_task: asyncio.Task | None = None

    # ---- shutdown: the last chance to save anything ----------------------
    async def finalize() -> None:
        # About ten seconds before the process is killed, so one batched write,
        # not a loop of them.
        if flush_task is not None:
            flush_task.cancel()

        summary = None
        if config.generate_summary:
            summary = await generate_summary(session, transcript.turns)

        await transcript.flush(summary=summary, call_status="completed")
        await backend.close()
        logger.info("Call %s ended, %d turn(s) stored", call_id, len(transcript.turns))

    ctx.add_shutdown_callback(finalize)

    await session.start(agent=Assistant(build_instructions(context)), room=ctx.room)

    # The lead is connected and audio is flowing. Record that, but never let a
    # slow or failed database write end a live call: the periodic flush and
    # the shutdown hook will retry, and the conversation matters more than
    # the status field. On the first real run a fifteen second machine stall
    # timed this write out, the exception escaped, and the job was abandoned
    # with the lead still on the line.
    try:
        await transcript.flush(call_status="in-progress")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not mark call in-progress (continuing anyway): %s", exc)

    async def flush_loop() -> None:
        """
        Periodic save while the call is live.

        Without this, a crashed worker loses the whole conversation. With it,
        the most you lose is the last few seconds.
        """
        while True:
            await asyncio.sleep(config.flush_interval_seconds)
            try:
                await transcript.flush()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Periodic flush failed: %s", exc)

    # `nonlocal` because finalize() closes over this name, declared above.
    flush_task = asyncio.create_task(flush_loop())  # noqa: F841 - read in finalize()

    await session.generate_reply(instructions=build_greeting(context))


if __name__ == "__main__":
    cli.run_app(server)
