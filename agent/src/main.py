"""
AI Voice Platform v2 agent.

Joins the LiveKit room for one call, holds the conversation, and stores the
transcript through the backend.

Run locally:
    python -m src.main dev

Run in production (LiveKit Cloud, Fly.io, or any Linux host):
    python -m src.main start

Who does what, because this confuses everyone:
    LiveKit   the room that carries audio. Not the agent.
    Sarvam    the ears and the voice. Not the agent.
    LLM       the brain. OpenAI by default, Groq or Sarvam by config.
    THIS FILE the agent.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterable, NoReturn

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RunContext,
    StopResponse,
    cli,
    function_tool,
    get_job_context,
)
from livekit import api as lk_api
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.plugins import sarvam, silero

from .backend_client import BackendClient, call_id_from_room
from .config import config
from .language import (
    FALLBACK,
    NOISY_CLOSE,
    SILENT,
    UNCLEAR,
    could_be_marker,
    detect_choice,
    detect_named_choice,
    has_speakable_letters,
    language_name,
    looks_foreign,
    marker_of,
    meaningful_words,
    mentions_language_request,
    mentions_platform,
    mentions_time,
    sanitise,
)
from .slots import resolve_slot
from .prompts import (
    LANGUAGES,
    SUMMARY_PROMPT,
    booking_zone,
    build_greeting,
    build_instructions,
    idle_close_line,
    idle_prompt_line,
    offered_codes,
    offered_spoken,
    script_rule,
)

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s | %(message)s"

# Video platforms the backend may offer, as spoken to the lead.
_PLATFORM_LABELS = {"zoom": "Zoom", "google": "Google Meet"}
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# agent/src/main.py -> agent/src -> agent/agent.log
LOG_PATH = Path(__file__).resolve().parent.parent / "agent.log"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
logger = logging.getLogger("agent")


def attach_file_log() -> None:
    """
    Mirror everything to agent/agent.log as well as the console.

    The console window scrolls, and a crash that matters is usually several
    hundred lines above where you are looking. Called again from the worker
    setup and from each job, because LiveKit's CLI reconfigures logging after
    import and each job runs in its own process. Guarded so it never attaches
    twice.
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
    """Load the voice activity detector once per worker process, not per call."""
    attach_file_log()
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD loaded. Voice stack: %s", config.describe())
    if config.llm_provider == "groq":
        # Seen on a real call: 92 rate-limit refusals, 18 second replies,
        # a lost turn, and the silence timer closing the call. Groq's free
        # tier allows 8,000 tokens a minute. The compact prompt, the trimmed
        # history and the longer retries keep a normal call under that, but
        # a fast talker or a long call can still touch it.
        logger.warning(
            "LLM_PROVIDER=groq: the free tier allows 8,000 tokens per minute. Each turn "
            "now costs about 1,200, so a normal call fits; if the log shows 429s, lower "
            "AGENT_HISTORY_ITEMS, add billing on Groq (Dev tier), or use LLM_PROVIDER=openai."
        )


server.setup_fnc = prewarm


# ---------------------------------------------------------------------------
# Noise cancellation
#
# LiveKit's BVC model strips background talk, TV and traffic from the lead's
# audio before it reaches speech-to-text. On the first noisy test call, 42
# seconds of other people's conversation was transcribed as the lead, and the
# greeting waited politely for all of it to finish. This is the fix for that.
#
# The plugin is a separate package and only works against LiveKit Cloud, which
# is what this project uses. If it is missing, the agent runs without it and
# says so once at startup rather than refusing to start.
# ---------------------------------------------------------------------------

try:
    from livekit.plugins import noise_cancellation as _nc

    def room_input_options() -> RoomInputOptions:
        return RoomInputOptions(noise_cancellation=_nc.BVC())

    _NC_STATUS = "on (LiveKit BVC)"
except ImportError:  # pragma: no cover - depends on the installed extras

    def room_input_options() -> RoomInputOptions:
        return RoomInputOptions()

    _NC_STATUS = "OFF (livekit-plugins-noise-cancellation not installed)"


# ---------------------------------------------------------------------------
# Junk transcript filter
#
# Speech-to-text guessing at noise produces lines like "ना ना ना ना ना ना" or
# "लोग लोग लोग लोग". Sending those to the brain wastes a turn, confuses the
# conversation, and costs money. This catches the obvious shapes.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\S+")


def looks_like_junk(text: str) -> bool:
    words = _WORD_RE.findall(text)
    if not words:
        return True
    if len(words) >= 6:
        distinct = len(set(words))
        # Six or more words with almost no variety is a stuck transcriber,
        # not a person. "ना ना ना ना ना ना" has 6 words and 1 distinct.
        if distinct <= max(2, len(words) // 6):
            return True
    return False


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
            {"role": role, "text": text, "at": moment.isoformat(), "interrupted": interrupted}
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
# Hanging up
#
# Ending the call from the agent's side means deleting the room, which
# disconnects the lead's browser (or the carrier leg) as well, and then
# shutting this job down so the transcript and summary are written. Just
# shutting the job would leave the lead staring at a live call screen with
# nobody in it, which is the "in-progress after hang-up" bug from earlier.
# ---------------------------------------------------------------------------


async def hang_up(reason: str) -> None:
    job = get_job_context()
    room_name = job.room.name
    logger.info("Hanging up: %s", reason)
    try:
        await job.api.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception as exc:  # noqa: BLE001
        # If the room is already gone (lead hung up first) this is expected.
        logger.info("Room %s not deleted (%s); shutting down anyway", room_name, exc)
    job.shutdown(reason=reason)


# ---------------------------------------------------------------------------
# The assistant
# ---------------------------------------------------------------------------


class Assistant(Agent):
    """
    Maya, with the language rules enforced in code.

    The first real test showed what happens when language is left to the
    brain: it skipped the switch when the lead chose English, then flipped to
    Hindi on its own because one noise transcript came through in Devanagari.
    So now:

      - The lead's choice is detected here, from what they said or the script
        they said it in, and the ears, voice and system prompt are switched
        without asking the brain.
      - After that, a transcript mostly in another script never reaches the
        brain. Once is silence; twice in a row and she says, in the call's
        language, that she did not catch that.
      - The brain's own switch_language tool only works if the lead's last
        sentence actually asked for a language change.
      - Whatever the brain writes is filtered before the voice reads it, so a
        stray line in the wrong script cannot make the voice fail. If nothing
        speakable survives, she says a fixed sentence in the right language.
      - The brain judges every transcript before answering. Speech that was
        not addressed to Maya (people nearby, a television) comes back as the
        single word SILENT, and the voice says nothing. Turns she cannot use,
        in a row, climb a ladder: silence, "did not catch that", the offer of
        a callback, then a fixed goodbye and the call ends. She never sits
        arguing with a television for ten minutes.
      - She ends the call herself, through end_call, once she has said
        goodbye. The room is closed, so the lead's screen ends too.
    """

    # After this many unusable turns in a row she speaks up rather than
    # sitting silent while the lead wonders whether the line is dead.
    _SPEAK_UP_AFTER = 2

    def __init__(
        self,
        context: dict[str, Any],
        *,
        lead_id: str,
        language: str,
        offered: list[str],
        backend: BackendClient,
    ) -> None:
        super().__init__(instructions=build_instructions(context))
        self._context = context
        self.lead_id = lead_id
        self.language = language
        self.language_chosen = False
        self._offered = offered
        self._backend = backend
        self._call_id = str(context.get("call_id") or "")
        self._last_user_text = ""
        # The last few things the lead said, as the ears heard them. This is
        # what book_slot checks before it believes the brain: a slot may
        # only be booked when a day or a time appears in the lead's own
        # words. It stops the brain deciding a time on its own.
        self._recent_user: list[str] = []
        self._unclear_answers = 0
        self._unusable_in_a_row = 0
        self._ending = False
        self._booked = False
        self._booked_at = ""
        self._booked_said = ""
        self._notes_saved = 0
        # Video platforms the backend can make links on, default first, and
        # whether the lead has been asked to choose between them.
        self._platforms = [p for p in (context.get("meeting_platforms") or []) if p in _PLATFORM_LABELS]
        self._platform_asked = False
        # Turns since the language was chosen. In the first couple, a bare
        # language name ("English") corrects a wrong choice without the lead
        # having to phrase a request.
        self._turns_since_choice = 0

    @property
    def ending(self) -> bool:
        return self._ending

    def mark_ending(self) -> None:
        """Goodbye is being said. Everything heard from now on is ignored."""
        self._ending = True

    # ---- language plumbing -------------------------------------------------

    def _apply_language(self, code: str) -> None:
        """Point the ears and the voice at one language. Never raises."""
        session = self.session
        switched: list[str] = []
        for attr, kwargs in (("tts", {"target_language_code": code}), ("stt", {"language": code})):
            component = getattr(session, attr, None)
            if component is not None and hasattr(component, "update_options"):
                try:
                    component.update_options(**kwargs)
                    switched.append(attr)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s language switch to %s failed: %s", attr, code, exc)
        self.language = code
        logger.info("Language set to %s (%s)", code, ", ".join(switched) or "voice filter only")

    async def _choose_language(self, code: str, how: str, turn_ctx: ChatContext | None = None) -> None:
        """
        The lead has chosen. Switch ears and voice, rewrite the brain's brief
        with the language baked in, and, when called from inside a turn, tell
        the brain in that same turn so the very next reply is already right.
        """
        self._apply_language(code)
        self.language_chosen = True
        self._turns_since_choice = 0
        await self.update_instructions(build_instructions(self._context, code))
        if turn_ctx is not None:
            turn_ctx.add_message(
                role="system",
                content=(
                    f"The lead has chosen {language_name(code)}. Ears and voice are now set to it. "
                    f"Reply in {language_name(code)} from this turn on. {script_rule(code)} "
                    f"Language is settled; do not ask about it again. Continue with the first "
                    f"step of your instructions not yet done."
                ),
            )
        logger.info("Lead chose %s (%s)", language_name(code), how)

    # ---- the unusable-turn ladder --------------------------------------------

    def _fixed_line(self, table: dict[str, str]) -> str:
        return table.get(self.language, table["en-IN"])

    async def _unusable(self, why: str, text: str, *, spoke: bool = False) -> None:
        """
        One more turn Maya could not use. Climb the ladder:

            1st  say nothing if it was not for her; "did not catch that" if
                 it was for her but made no sense (spoke=True)
            2nd  "did not catch that" either way
            Nth  fixed goodbye, hang up (N = AGENT_UNCLEAR_TURNS_BEFORE_CLOSE)

        A usable turn in between resets the count.
        """
        self._unusable_in_a_row += 1
        n = self._unusable_in_a_row
        logger.info("Unusable turn, %s (%d in a row): %r", why, n, text[:60])

        if n >= config.unclear_turns_before_close:
            await self._close_noisy_call()
        elif not spoke and n >= self._SPEAK_UP_AFTER:
            try:
                self.session.say(self._fixed_line(FALLBACK), allow_interruptions=False)
            except Exception as exc:  # noqa: BLE001
                logger.info("Could not speak the fallback line: %s", exc)

    def _heard(self, text: str) -> None:
        """Remember what the lead said, for the tools' guards."""
        self._last_user_text = text
        if text:
            self._recent_user.append(text)
            del self._recent_user[:-6]

    def _usable(self, text: str) -> None:
        self._unusable_in_a_row = 0
        self._heard(text)

    async def _close_noisy_call(self) -> None:
        """Deterministic exit when the line has been unusable for too long."""
        if self._ending:
            return
        self._ending = True
        logger.info("Line unusable for %d turns, closing the call", self._unusable_in_a_row)
        try:
            handle = self.session.say(self._fixed_line(NOISY_CLOSE), allow_interruptions=False)
            await handle.wait_for_playout()
        except Exception as exc:  # noqa: BLE001
            logger.info("Noisy-close line not spoken: %s", exc)
        await hang_up("line unusable: background noise or garbled audio")

    def _drop(self, why: str, text: str) -> NoReturn:
        """Drop the turn before the brain sees it. Counts on the ladder."""
        asyncio.create_task(self._unusable(why, text))
        raise StopResponse()

    # ---- hooks -------------------------------------------------------------

    def _trim_history(self, turn_ctx: ChatContext) -> None:
        """
        Send the brain only the last few conversation items this turn.

        turn_ctx is a copy used for this one reply, so the stored transcript
        is untouched. The instructions stay; older exchanges go. This is what
        keeps a whole call inside Groq's free tier: the prompt and tools cost
        about 1,100 tokens a turn, the transcript is the part that grows.
        A short note tells the brain something was cut so it does not treat
        the truncated start as the start of the call and restart the script.
        """
        keep = config.history_items
        if keep <= 0:
            return
        try:
            before = len(turn_ctx.items)
            if hasattr(turn_ctx, "truncate"):
                turn_ctx.truncate(max_items=keep)
            else:
                items = turn_ctx.items
                system = [i for i in items if getattr(i, "role", None) == "system"]
                rest = [i for i in items if getattr(i, "role", None) != "system"][-keep:]
                # Never start on a tool result whose call was cut off.
                while rest and getattr(rest[0], "type", "") in ("function_call", "function_call_output"):
                    rest.pop(0)
                items[:] = system + rest
            cut = before - len(turn_ctx.items)
            if cut > 0:
                turn_ctx.add_message(
                    role="system",
                    content=(
                        "Earlier turns are not shown. Everything before this point is done; "
                        "continue from the current stage, never restart the script."
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.info("Could not trim history: %s", exc)

    def _progress_line(self) -> str:
        """One line of facts the code knows for certain, sent every turn."""
        if self._booked:
            slot = f"a slot IS booked ({self._booked_said}); do not book again"
        else:
            slot = "no slot booked yet"
        return f"Progress: language {language_name(self.language)}; {slot}; notes saved: {self._notes_saved}."

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """
        Runs after the lead's turn is transcribed, before the brain sees it.
        Raising StopResponse drops the turn: no reply, no LLM call.
        """
        text = (new_message.text_content or "").strip()

        if self._ending:
            # Goodbye has been said. Nothing heard now changes anything.
            raise StopResponse()

        if looks_like_junk(text):
            self._drop("junk", text)

        self._trim_history(turn_ctx)
        turn_ctx.add_message(role="system", content=self._progress_line())

        if not self.language_chosen:
            code = detect_choice(text, self._offered)
            if code:
                self._usable(text)
                await self._choose_language(code, f"from {text[:40]!r}", turn_ctx)
                return
            # Not a choice. The prompt makes the brain ask once more; after
            # that, rather than loop forever, settle on the greeting language
            # and get on with the call.
            self._unclear_answers += 1
            if self._unclear_answers >= 2:
                await self._choose_language(
                    config.greeting_language, "defaulted after unclear answers", turn_ctx
                )
            self._heard(text)
            return

        # Right after the choice, a plain language name corrects it. "Hmm"
        # was once taken as Hindi and the lead's "English" was then refused;
        # this is the fix for that.
        self._turns_since_choice += 1
        if self._turns_since_choice <= 3:
            named = detect_named_choice(text, self._offered)
            if named and named != self.language and len(text.split()) <= 4:
                self._usable(text)
                await self._choose_language(named, f"corrected from {text[:40]!r}", turn_ctx)
                return
            # A whole sentence in another offered language, right after the
            # choice, is the lead telling us which language they actually
            # speak. Seen on a call: "no no" was read as Hindi, and the lead
            # then spoke English for the rest of the call while Maya did not.
            by_script = detect_choice(text, self._offered)
            if by_script and by_script != self.language and len(meaningful_words(text)) >= 4:
                self._usable(text)
                await self._choose_language(by_script, f"corrected by script from {text[:40]!r}", turn_ctx)
                return

        if looks_foreign(text, self.language):
            self._drop("foreign-script", text)

        # A usable turn as far as the code can tell. The brain makes the
        # final judgement and answers SILENT if it was not for Maya; the
        # voice filter below counts that on the same ladder.
        self._heard(text)

    async def tts_node(self, text: AsyncIterable[str], model_settings: Any):
        """
        Filter the brain's words before the voice reads them.

        Three jobs, in order:
          - If the reply is the word SILENT, say nothing: the brain decided
            the transcript was not addressed to Maya. If it is UNCLEAR, say
            the fixed "did not catch that" line for the language instead.
          - Characters outside the call language's script (Latin is always
            allowed) are removed piece by piece as the reply streams.
          - If the whole reply had nothing the voice could say, the fixed
            fallback sentence for the language is spoken instead, so the lead
            never hears silence in place of an answer.
        """
        marker: str | None = None

        async def filtered() -> AsyncIterable[str]:
            nonlocal marker
            head = ""
            deciding = True
            speakable = False
            removed = 0
            async for piece in text:
                if marker:
                    continue  # drain the stream, say nothing more
                if deciding:
                    # Hold the first characters back until we know whether
                    # this reply is one of the one-word markers.
                    head += piece
                    if could_be_marker(head) and len(head.strip()) < len(UNCLEAR) + 1:
                        continue
                    deciding = False
                    marker = marker_of(head)
                    if marker:
                        continue
                    piece, head = head, ""
                clean = sanitise(piece, self.language)
                removed += len(piece) - len(clean)
                if not speakable and has_speakable_letters(clean, self.language):
                    speakable = True
                if clean:
                    yield clean
            if deciding and head and not marker:
                # The whole reply arrived before a decision: it is short.
                marker = marker_of(head)
                if not marker:
                    clean = sanitise(head, self.language)
                    speakable = has_speakable_letters(clean, self.language)
                    if clean:
                        yield clean
            if marker == SILENT:
                return
            if marker == UNCLEAR:
                yield self._fixed_line(FALLBACK)
                return
            if removed:
                logger.info("Voice filter removed %d wrong-script character(s) for %s", removed, self.language)
            if not speakable:
                logger.warning("Reply had nothing the %s voice could say; speaking the fallback line", self.language)
                yield self._fixed_line(FALLBACK)

        async for frame in Agent.default.tts_node(self, filtered(), model_settings):
            yield frame

        if marker == SILENT:
            await self._unusable("not addressed to Maya", self._last_user_text)
        elif marker == UNCLEAR:
            await self._unusable("addressed to Maya but unclear", self._last_user_text, spoke=True)
        else:
            self._unusable_in_a_row = 0

    # ---- tools -------------------------------------------------------------

    @function_tool()
    async def switch_language(self, context: RunContext, language: str) -> str:
        """
        Change the call language, ONLY when the lead asked for it in words.
        language is the English name: english, hindi, telugu.
        """
        wanted = language.strip().lower()
        code = LANGUAGES.get(wanted)
        if not code or code not in self._offered:
            return (
                f"{language} is not offered on this call. Tell the lead so in one "
                f"sentence and offer {offered_spoken()}. Stay in {language_name(self.language)}."
            )

        # The guard. The tool does nothing unless the lead's last sentence
        # both named a language and asked for it.
        if self.language_chosen and not mentions_language_request(self._last_user_text):
            logger.info(
                "Refused switch to %s: the lead did not ask for it (last heard %r)",
                code,
                self._last_user_text[:60],
            )
            return (
                f"Not switching. The lead did not ask to change language. "
                f"Continue in {language_name(self.language)}."
            )

        await self._choose_language(code, "lead asked in words")
        return (
            f"Switched to {language_name(code)}. From now on {script_rule(code)} "
            f"Stay in {language_name(code)} until the lead asks for another language."
        )

    @function_tool()
    async def book_slot(
        self,
        context: RunContext,
        day: str,
        time: str,
        platform: str | None = None,
        notes: str | None = None,
    ) -> str:
        """
        Book the counsellor session once the lead has said a day and a time.
        day: the day exactly as the lead said it, for example "tomorrow",
        "Wednesday", "22 September". time: the time exactly as they said it,
        for example "6:30 pm", "half past six", "ten in the morning". Do not
        convert or calculate anything; the system does that. platform:
        "zoom" or "google" only if the lead asked for that one by name;
        leave it empty when they said anything is fine or were not asked.
        notes: questions for the counsellor, in English. Say only what the
        result tells you.
        """
        said = f"{day.strip()} {time.strip()}".strip()

        # The platform, only if the lead actually named it. "Anything is
        # fine" or no answer means the default platform; the brain does not
        # get to pick Zoom on the lead's behalf.
        wanted = (platform or "").strip().lower() or None
        heard = mentions_platform(" ".join(self._recent_user[-4:]))
        if wanted and heard is None:
            logger.info("Ignoring platform %r: the lead did not name one", wanted)
            wanted = None
        elif wanted and heard and heard not in wanted:
            logger.info("Platform %r from the brain, but the lead said %r; using the lead's", wanted, heard)
            wanted = heard

        # When two platforms are offered, the lead must be asked exactly
        # once. On a real call the brain skipped the question and booked
        # with a guess; the guard above dropped the guess, but the lead was
        # never asked. So the first booking attempt without an answer from
        # the lead is refused with the question to ask. The second attempt
        # goes through with whatever they said, or the default if they did
        # not mind.
        if len(self._platforms) >= 2 and heard is None and not self._platform_asked:
            self._platform_asked = True
            names = [_PLATFORM_LABELS[p] for p in self._platforms[:2]]
            logger.info("Refused book_slot: the lead has not been asked %s or %s yet", *names)
            return (
                f"Not booked yet. First ask the lead, in one sentence, whether they prefer "
                f"{names[0]} or {names[1]} for the session. Then call book_slot again with the "
                f"same day and time, and platform set to their answer, or left empty if they say "
                f"anything is fine."
            )
        if heard:
            self._platform_asked = True
        # Small models write "None" or "null" when there is nothing to say;
        # that must not land on the dashboard as a note.
        if notes and notes.strip().lower() in ("none", "null", "n/a", "na", "nil", "nothing", ""):
            notes = None

        # The guard. The brain does not get to decide the time. Unless the
        # lead named a day or a time recently, in any of the call's
        # languages, nothing is booked and the brain is told to ask.
        recent = " ".join(self._recent_user[-4:])
        if not mentions_time(recent):
            logger.info("Refused book_slot(%r): the lead has not said a time (recent: %r)", said, recent[:80])
            return (
                "Not booked. The lead has not said a day and a time in their own words. "
                "Do not guess or suggest a time. Ask them, in one sentence, which day and "
                "what time would suit them, then wait for their answer."
            )

        # The arithmetic, in code. Small models turned "Wednesday six thirty"
        # into a date six months in the past; this never will.
        when, problem = resolve_slot(
            day,
            time,
            now=datetime.now(booking_zone()),
            work_start=config.work_start_hour,
            work_end=config.work_end_hour,
        )
        if problem:
            logger.info("book_slot(%r) needs more: %s", said, problem)
            return f"Not booked yet. {problem}"
        assert when is not None
        iso = when.isoformat(timespec="minutes")

        if self._booked and self._booked_at == iso:
            return (
                "This slot is already booked; do not book it again. Tell the lead it is "
                "confirmed, then ask if there is anything else."
            )

        ok, message = await self._backend.book_slot(
            lead_id=self.lead_id,
            call_id=self._call_id,
            scheduled_at=iso,
            requested_text=said,
            notes=notes,
            meeting_platform=wanted,
        )
        if ok:
            self._booked = True
            self._booked_at = iso
            self._booked_said = said
            logger.info("Slot booked for lead %s: %s (%r)", self.lead_id, iso, said)
            return (
                f"{message} Tell the lead the day and time is confirmed, in one sentence, "
                f"and repeat exactly what this result says about the WhatsApp link. "
                f"Then ask if there is anything else."
            )
        logger.info("Slot not booked for lead %s: %s", self.lead_id, message)
        return message

    @function_tool()
    async def note_for_counsellor(self, context: RunContext, notes: str) -> str:
        """
        Save a question you must not answer (fees, eligibility, dates, other
        courses) or a callback request for the counsellor, in English. Not
        for the slot time; that is book_slot.
        """
        ok = await self._backend.save_callback(lead_id=self.lead_id, callback_notes=notes)
        if ok:
            self._notes_saved += 1
            logger.info("Note saved for lead %s: %r", self.lead_id, notes)
            return "Noted for the counsellor. Say so in a few words and continue."
        return "Could not save right now. Say the counsellor will cover it, and continue."

    @function_tool()
    async def end_call(self, context: RunContext) -> str:
        """
        End the call, only AFTER you have said goodbye. Your goodbye finishes
        playing before the line closes.
        """
        if self._ending:
            return "The call is already ending."
        self._ending = True
        logger.info("Brain asked to end the call")
        try:
            # Let the goodbye finish. RunContext.wait_for_playout waits for
            # the speech that carried this tool call.
            await context.wait_for_playout()
        except Exception as exc:  # noqa: BLE001
            logger.info("Could not wait for the goodbye to finish: %s", exc)
        await hang_up("conversation complete")
        return "Call ended."


# ---------------------------------------------------------------------------
# Phone calls: wait for the lead to pick up
#
# On the phone path the backend asks LiveKit to dial the lead into this room
# through Plivo. The room exists, and this job starts, while the phone is
# still ringing. Greeting into a ringing line means the lead answers to
# silence or to the middle of a sentence, so Maya waits for the phone
# participant to turn "active" and only then speaks. If nobody answers, the
# call is recorded as no-answer and the room is closed.
# ---------------------------------------------------------------------------

# Values of the `sip.callStatus` participant attribute that LiveKit sets.
_SIP_ACTIVE = {"active", "automation"}
_SIP_OVER = {"hangup"}


async def wait_for_answer(ctx: JobContext, timeout: float) -> str:
    """
    Returns "answered", "no-answer" or "browser".

    "browser" means the first participant was not a SIP participant at all,
    which is the browser path: nothing to wait for.
    """
    from livekit import rtc

    participant = await ctx.wait_for_participant()
    if participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        return "browser"

    identity = participant.identity
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        current = ctx.room.remote_participants.get(identity)
        if current is None:
            return "no-answer"  # LiveKit removed the leg: busy, rejected, timed out
        status = current.attributes.get("sip.callStatus", "")
        if status != last:
            logger.info("Phone leg %s: %s", identity, status or "(no status yet)")
            last = status
        if status in _SIP_ACTIVE:
            return "answered"
        if status in _SIP_OVER:
            return "no-answer"
        await asyncio.sleep(0.25)
    return "no-answer"


# ---------------------------------------------------------------------------
# The brain
# ---------------------------------------------------------------------------


def build_llm():
    """
    Chosen by LLM_PROVIDER. Every provider goes through livekit-plugins-openai,
    because all four speak the OpenAI wire protocol (streaming and tool calls
    included); only the base URL, key and model name differ.

    Sarvam is deliberately not routed through livekit-plugins-sarvam's own LLM
    class. That class pins the model name to a fixed list and, on the version
    we hit, called an endpoint that answered 400 "currently in beta". Sarvam's
    v1 chat completions endpoint is generally available and OpenAI
    compatible, so the plain OpenAI client pointed at it is the safer path,
    and it lets us use sarvam-105b-conversations, the variant Sarvam built
    for voice agents.
    """
    from livekit.plugins import openai as openai_plugin

    if config.llm_provider == "sarvam":
        import openai as openai_sdk

        # Sarvam accepts either "Authorization: Bearer <key>" or its own
        # "api-subscription-key" header. Send both so a change on their side
        # in either direction keeps working.
        client = openai_sdk.AsyncOpenAI(
            api_key=config.sarvam_api_key,
            base_url="https://api.sarvam.ai/v1",
            default_headers={"api-subscription-key": config.sarvam_api_key},
        )
        return openai_plugin.LLM(model=config.llm_model, client=client)

    if config.llm_provider == "groq":
        return openai_plugin.LLM(
            model=config.groq_model,
            api_key=config.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    if config.llm_provider == "gemini":
        # Google serves Gemini on an OpenAI compatible endpoint, streaming
        # and tool calls included, so the same plugin covers it.
        return openai_plugin.LLM(
            model=config.gemini_model,
            api_key=config.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    return openai_plugin.LLM(model=config.openai_model, api_key=config.openai_api_key)


async def generate_summary(session: AgentSession, turns: list[dict[str, Any]]) -> str | None:
    """Closing summary for the CRM record. Best effort; never costs the transcript."""
    if not turns:
        return None

    transcript = "\n".join(
        f"{'Assistant' if t['role'] == 'assistant' else 'Lead'}: {t['text']}" for t in turns
    )

    try:
        chat_ctx = ChatContext()
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

    # The room name is on the JOB and readable before any connect. This differs
    # from the Node SDK, where it is empty until the room is connected.
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
            "Check BACKEND_BASE_URL is reachable (%s) and AGENT_API_KEY matches the backend.",
            config.backend_base_url,
        )
        await backend.close()
        return

    logger.info(
        "Call %s | lead %s | enquiry about %s | %s | noise cancellation %s | live language switch: tts=%s stt=%s",
        call_id,
        context["name"],
        context["product_or_course"],
        config.describe(),
        _NC_STATUS,
        hasattr(sarvam.TTS, "update_options"),
        hasattr(sarvam.STTRealtime, "update_options"),
    )

    transcript = Transcript(call_id, backend)

    # Phone path: do not say a word until the lead has picked up.
    if context.get("transport") == "phone":
        await ctx.connect()
        logger.info("Phone call: waiting up to %ds for the lead to answer", config.answer_timeout_seconds)
        outcome = await wait_for_answer(ctx, config.answer_timeout_seconds)
        if outcome == "no-answer":
            logger.info("Call %s not answered", call_id)
            try:
                await transcript.flush(call_status="no-answer")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not record no-answer: %s", exc)
            await backend.close()
            await hang_up("no answer")
            return
        logger.info("Call %s answered (%s)", call_id, outcome)

    # Voice starts in the greeting language (English by default): she
    # introduces herself and asks which language to continue in. Ears start
    # in the configured STT language; hi-IN codemix has transcribed English,
    # Hindi and Telugu answers correctly in testing, which is all the opening
    # question needs. The Assistant switches both the moment it detects the
    # lead's answer.
    language = config.greeting_language
    offered = offered_codes()
    logger.info(
        "Greeting in %s, offering %s, ears on %s",
        language_name(language),
        offered_spoken(),
        config.stt_language,
    )

    # Turn timing and interruption policy. The defaults wait a long time to
    # be sure the lead has finished, which reads as slow, and stop Maya for
    # any 0.7 seconds of sound, which reads as her breaking off mid-sentence
    # whenever a TV is on. These are the production settings; each one is
    # passed only if the installed framework version accepts it, and the
    # startup log says which were applied.
    turn_settings: dict[str, Any] = {
        "min_endpointing_delay": config.min_endpointing_delay,
        "max_endpointing_delay": config.max_endpointing_delay,
        "min_interruption_duration": config.min_interruption_duration,
        "min_interruption_words": config.min_interruption_words,
        "false_interruption_timeout": config.false_interruption_timeout,
        "resume_false_interruption": config.resume_false_interruption,
        # Start generating the reply while the transcript is still being
        # finalised. Saves a few hundred milliseconds on every turn.
        "preemptive_generation": True,
    }
    accepted = inspect.signature(AgentSession.__init__).parameters
    applied = {k: v for k, v in turn_settings.items() if k in accepted}
    skipped = sorted(set(turn_settings) - set(applied))
    logger.info(
        "Turn settings applied: %s%s",
        ", ".join(f"{k}={v}" for k, v in applied.items()),
        f" | not supported by this livekit-agents: {', '.join(skipped)}" if skipped else "",
    )

    # The voice. temperature is what makes bulbul:v3 sound warm rather than
    # read; older plugin versions do not accept it, so it is passed only when
    # the installed one does.
    tts_kwargs: dict[str, Any] = {
        "target_language_code": language,
        "model": config.tts_model,
        "speaker": config.tts_speaker,
        "pace": config.tts_pace,
    }
    if "temperature" in inspect.signature(sarvam.TTS.__init__).parameters:
        tts_kwargs["temperature"] = config.tts_temperature
    else:
        logger.info("Installed Sarvam plugin has no TTS temperature; upgrade it for a warmer voice")

    # Rate limits. The framework retries a failed brain request three times,
    # two seconds apart, then gives up on the turn. Groq's free tier answers
    # 429 with "try again in about six seconds", so those retries all fail
    # and the turn is lost: the lead gets "did not catch that" and repeats
    # themselves, which is where the repeated questions came from. Waiting
    # longer between more tries gets the reply through instead. Passed only
    # if this framework version accepts it.
    # Turn detection. "vad" ends the lead's turn on silence alone, which is
    # the fastest path. The framework's turn-detector model was timing out
    # against LiveKit's cloud on a real call ("eot prediction timed out",
    # "cloud turn detector failed") and cost two to four seconds a reply.
    if config.turn_detection != "auto" and "turn_detection" in accepted:
        applied["turn_detection"] = config.turn_detection
    logger.info("Turn detection: %s", config.turn_detection)

    if "conn_options" in accepted:
        try:
            from livekit.agents import APIConnectOptions

            try:
                from livekit.agents.voice import SessionConnectOptions
            except ImportError:
                from livekit.agents.voice.agent_session import SessionConnectOptions

            applied["conn_options"] = SessionConnectOptions(
                llm_conn_options=APIConnectOptions(
                    max_retry=config.llm_max_retries,
                    retry_interval=config.llm_retry_interval,
                ),
            )
            logger.info(
                "Brain retries: up to %d, %.1fs apart", config.llm_max_retries, config.llm_retry_interval
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Could not set brain retry options (framework default applies): %s", exc)
    logger.info(
        "History sent to the brain per turn: %s items",
        config.history_items if config.history_items > 0 else "all",
    )

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=sarvam.STTRealtime(
            language=config.stt_language,
            mode=config.stt_mode,
            stream_type=config.stt_stream_type,
        ),
        llm=build_llm(),
        tts=sarvam.TTS(**tts_kwargs),
        **applied,
    )

    # Timestamp of the last thing either side said. The idle watchdog below
    # reads it. Plain def, not async: AgentSession emits synchronously.
    last_activity = {"at": time.monotonic()}

    @session.on("conversation_item_added")
    def _on_item(event: ConversationItemAddedEvent) -> None:
        item = event.item
        if not isinstance(item, ChatMessage):
            return

        text = (item.text_content or "").strip()
        if not text:
            return

        role = "assistant" if item.role == "assistant" else "user"
        if role == "assistant":
            marker = marker_of(text)
            if marker == SILENT:
                return  # nothing was spoken, nothing to store
            if marker == UNCLEAR:
                # What the lead actually heard was the fixed fallback line.
                text = FALLBACK.get(assistant.language, FALLBACK["en-IN"])

        last_activity["at"] = time.monotonic()
        transcript.add(role, text, bool(item.interrupted), item.created_at)

    # Felt latency: the gap between the lead's last word and Maya's first
    # sound. This is the number a human notices, so it is logged every turn
    # and tuned on, rather than guessed at.
    lead_stopped_at = {"t": 0.0}

    @session.on("user_state_changed")
    def _on_user_state(event: Any) -> None:
        if getattr(event, "new_state", None) == "listening" and getattr(event, "old_state", None) == "speaking":
            lead_stopped_at["t"] = time.monotonic()

    @session.on("agent_state_changed")
    def _on_agent_state(event: Any) -> None:
        # While Maya is thinking or speaking, the lead is not "silent". This
        # stops a slow brain from triggering the are-you-there check.
        if getattr(event, "new_state", None) in ("thinking", "speaking"):
            last_activity["at"] = time.monotonic()
        if getattr(event, "new_state", None) == "speaking" and lead_stopped_at["t"]:
            gap = time.monotonic() - lead_stopped_at["t"]
            lead_stopped_at["t"] = 0.0
            if gap < 30:
                logger.info("Response latency: %.2fs from lead's last word to Maya's first sound", gap)

    @session.on("error")
    def _on_error(event: Any) -> None:
        """
        The brain, ears or voice failed for a whole turn (retries exhausted).
        Silence here is the worst outcome: the lead thinks the line is dead.
        Say the fixed did-not-catch-that line so they speak again, and log
        the cause loudly; a rate limit shows up here as a 429.
        """
        err = getattr(event, "error", None)
        recoverable = getattr(err, "recoverable", False)
        source = type(getattr(event, "source", None)).__name__
        logger.error("Pipeline error from %s (recoverable=%s): %s", source, recoverable, err)
        if recoverable or assistant.ending:
            return
        try:
            session.say(FALLBACK.get(assistant.language, FALLBACK["en-IN"]), allow_interruptions=True)
        except Exception as exc:  # noqa: BLE001
            logger.info("Could not speak after pipeline error: %s", exc)

    flush_task: asyncio.Task | None = None
    idle_task: asyncio.Task | None = None

    # ---- shutdown: the last chance to save anything ----------------------
    async def finalize() -> None:
        for task in (flush_task, idle_task):
            if task is not None:
                task.cancel()

        summary = None
        if config.generate_summary:
            summary = await generate_summary(session, transcript.turns)

        await transcript.flush(summary=summary, call_status="completed")
        await backend.close()
        logger.info("Call %s ended, %d turn(s) stored", call_id, len(transcript.turns))

    ctx.add_shutdown_callback(finalize)

    assistant = Assistant(
        context,
        lead_id=context["lead_id"],
        language=language,
        offered=offered,
        backend=backend,
    )
    await session.start(agent=assistant, room=ctx.room, room_input_options=room_input_options())

    # Record that the lead is connected, but never let a slow database write
    # end a live call. The periodic flush and the shutdown hook will retry.
    try:
        await transcript.flush(call_status="in-progress")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not mark call in-progress (continuing anyway): %s", exc)

    async def flush_loop() -> None:
        """Periodic save while the call is live, so a crash loses seconds, not the call."""
        while True:
            await asyncio.sleep(config.flush_interval_seconds)
            try:
                await transcript.flush()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Periodic flush failed: %s: %s", type(exc).__name__, exc)

    async def idle_loop() -> None:
        """
        If the lead goes quiet, check once, then close politely.

        Without this a lead who walks away leaves Maya sitting in silence
        until they hang up, billing every second. With it: after
        AGENT_IDLE_PROMPT_SECONDS of silence she asks if they are still
        there; after AGENT_IDLE_HANGUP_SECONDS more she says goodbye and
        ends the call.
        """
        prompted = False
        while True:
            await asyncio.sleep(2)
            # The session closes when the lead hangs up; nothing left to do.
            if getattr(session, "agent_state", None) in (None, "initializing"):
                continue
            if session.agent_state in ("speaking", "thinking"):
                continue
            if assistant.ending:
                return
            quiet_for = time.monotonic() - last_activity["at"]

            if not prompted and quiet_for >= config.idle_prompt_seconds:
                prompted = True
                last_activity["at"] = time.monotonic()
                logger.info("Lead quiet for %.0fs, checking they are there", quiet_for)
                try:
                    # Fixed line, no brain round trip.
                    session.say(idle_prompt_line(assistant.language))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Idle prompt failed: %s", exc)

            elif prompted and quiet_for >= config.idle_hangup_seconds:
                logger.info("Still quiet after check-in, closing the call")
                assistant.mark_ending()
                try:
                    handle = session.say(idle_close_line(assistant.language), allow_interruptions=False)
                    await handle.wait_for_playout()
                except Exception as exc:  # noqa: BLE001
                    # "AgentSession isn't running" here just means the lead
                    # already hung up. Not worth a warning.
                    logger.info("Idle close skipped: %s", exc)
                await hang_up("lead went silent")
                return

    flush_task = asyncio.create_task(flush_loop())
    idle_task = asyncio.create_task(idle_loop())

    # Speak first, and do not let background noise delay or cut the greeting.
    # Fixed words through the voice directly: no brain round trip, so the
    # lead hears her the moment they pick up, and the same words every call.
    # (Gemini also refuses a brain request that has no user message yet,
    # which is exactly what a generated greeting would be.)
    # The greeting CAN be interrupted. When it could not, whatever the lead
    # said over it was thrown away ("skipping reply to user input"), so
    # their first answer was lost and the next thing they said was taken
    # as the language choice. The interruption thresholds (1.2 seconds and
    # three words) already stop a "hello?" or a television cutting her off.
    greeting = build_greeting(context)
    logger.info("Greeting: %s", greeting)
    handle = session.say(greeting, allow_interruptions=True)
    await handle.wait_for_playout()
    last_activity["at"] = time.monotonic()


if __name__ == "__main__":
    cli.run_app(server)
