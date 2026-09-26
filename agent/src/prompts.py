"""
Everything the agent says, and every rule that shapes it.

This is the only file that decides what Maya asks. Not Sarvam, not LiveKit,
not the carrier. If you want to change the conversation, change this file and
restart the agent. Nothing else needs to move.

Two rules here are compliance, not style:

  1. She announces she is an AI. India does not require this today, but a
     draft amendment covering AI-initiated calls has been pending since March
     2026 and this costs nothing.

  2. She stays strictly to the enquiry the lead submitted. The moment she
     mentions fees, discounts or other courses, the call turns from a SERVICE
     call into a PROMOTIONAL one, which needs a 140-series number and a
     heavier compliance regime. A landline-series number prohibits promotional
     content outright. Script discipline is what keeps the call lawful.
"""

from __future__ import annotations

from .config import config
from .language import language_name, script_of

# ---------------------------------------------------------------------------
# Languages
#
# The eleven languages Sarvam can both hear (saarika) and speak (bulbul).
# Keyed by the name a lead would say, valued by the Sarvam code. Which of
# these Maya offers on a call is AGENT_LANGUAGES in .env.
#
# Names, scripts, choice words and the fixed fallback sentences live in
# language.py, which is also what main.py enforces with. This file only turns
# them into prose for the brain.
#
# What is NOT here: Urdu, Assamese, Konkani, Nepali and the other scheduled
# languages. Sarvam does not speak them yet. If a lead asks for one, Maya says
# so and offers the nearest option; she never pretends.
# ---------------------------------------------------------------------------

LANGUAGES: dict[str, str] = {
    "hindi": "hi-IN",
    "english": "en-IN",
    "telugu": "te-IN",
    "tamil": "ta-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "marathi": "mr-IN",
    "bengali": "bn-IN",
    "bangla": "bn-IN",
    "gujarati": "gu-IN",
    "punjabi": "pa-IN",
    "odia": "od-IN",
    "oriya": "od-IN",
}

# Unicode block name -> the name a person uses for the script.
_SCRIPT_DISPLAY = {"ORIYA": "Odia"}


def offered_codes() -> list[str]:
    """Sarvam codes for the languages offered on this deployment, in order."""
    codes = [LANGUAGES[n] for n in config.offered_languages if n in LANGUAGES]
    return codes or ["en-IN", "hi-IN", "te-IN"]


def offered_names() -> list[str]:
    """The languages Maya offers on this deployment, capitalised for speech."""
    return [language_name(c) for c in offered_codes()]


def offered_spoken() -> str:
    """'English, Hindi or Telugu' for use inside a sentence."""
    names = offered_names()
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " or " + names[-1]


def script_rule(code: str) -> str:
    """
    One sentence telling the brain exactly what characters it may write.

    The voice for a language accepts ONLY that script plus Latin letters.
    Telugu text sent to a Hindi voice is rejected outright ("Text must contain
    at least one character from the allowed languages") and the lead hears
    silence. main.py strips wrong-script characters before the voice as a
    backstop, but a brain that writes the right script in the first place
    gives a far better sentence than one that has been cut.
    """
    name = language_name(code)
    block = script_of(code)
    script = _SCRIPT_DISPLAY.get(block, block.capitalize())
    if block == "LATIN":
        return "Write in English using Latin letters only."
    return (
        f"Write {name} in {script} script. English words, names and numbers may be "
        f"in Latin letters. Never write in any other script; the voice cannot read it."
    )


def booking_zone():
    """
    The booking timezone, with a fallback that cannot fail.

    Windows Python ships no timezone database; the `tzdata` package supplies
    it. If that package is missing, fall back to a fixed +05:30 so a call is
    never lost over a timezone lookup. Logged once so it gets fixed.
    """
    from datetime import timedelta, timezone as _tz
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(config.booking_timezone)
    except (ZoneInfoNotFoundError, ModuleNotFoundError):
        import logging

        logging.getLogger("agent").warning(
            "Timezone %s not found (install tzdata: agent\\.venv\\Scripts\\pip install tzdata). "
            "Using fixed +05:30 for now.",
            config.booking_timezone,
        )
        return _tz(timedelta(hours=5, minutes=30), "IST")


def current_time_line() -> str:
    """
    Today's date and the time right now, in the booking timezone, written
    the way the brain needs it to turn "tomorrow at six" into an exact
    moment. Rebuilt on every prompt, so a call that crosses midnight is
    still right.
    """
    from datetime import datetime, timedelta

    now = datetime.now(booking_zone())
    tomorrow = now + timedelta(days=1)
    return (
        f"Now: {now.strftime('%A')} {now.day} {now.strftime('%B')}, "
        f"{now.strftime('%I:%M %p').lstrip('0')}. Tomorrow is {tomorrow.strftime('%A')}. "
        f"You never calculate dates or times; pass the lead's words to book_slot and it does."
    )


def build_instructions(context: dict, language: str | None = None) -> str:
    """
    The system prompt for one specific call.

    Called twice per call. First with language=None, before the lead has
    chosen: the only job is to settle the language. Then again, by main.py,
    the moment the choice is detected, with the chosen code baked in, so the
    brain is never asked to remember a switch. It simply IS a Telugu call.
    """
    notes = (context.get("notes") or "").strip()
    notes_line = f"\n- What they wrote on the form: {notes}" if notes else ""

    name = context["name"]
    course = context["product_or_course"]
    now_line = current_time_line()
    counsellor_hours = config.counsellor_hours

    if language is None:
        lang_code = config.greeting_language
        lang = language_name(lang_code)
        opening = f"""Language: not chosen yet. Your greeting asked for {offered_spoken()}. Their first answer is the choice; the system detects it and switches your ears and voice, no tool needed. If the answer is not a language, ask once more in {lang}: "{offered_spoken()}?" Nothing else until then. {script_rule(lang_code)}"""
    else:
        lang_code = language
        lang = language_name(lang_code)
        opening = f"""Language: {lang}, chosen by the lead; settled, never ask again. Speak only {lang}. {script_rule(lang_code)} Call switch_language only if they ask in words. A language outside {offered_spoken()}: say you do not have it, offer the closest."""

    # Every word here is sent to the brain on every reply, so both versions
    # are kept tight. On Groq's free tier that is the difference between a
    # call that flows and one that hits the rate limit by turn six.
    platform_step = platform_instruction(context)

    if config.flow == "short":
        return _short_flow(name, course, notes_line, now_line, opening, lang, counsellor_hours, platform_step)

    return f"""You are {config.agent_name}, a female AI voice assistant calling for {config.agent_company}. Speaking with {name}, who enquired about {course}.{notes_line}
{now_line}
{opening}

Script, six stages, in order. Before each reply find the first stage not yet done and do only that one. A stage the lead has answered is done: never ask it again, in any words.
1 Identity: confirm it is {name}. Skip if already clear. Wrong number or not available: apologise, goodbye, end_call.
2 Interest: one question, what they want to know about {course}. Acknowledge the answer in a few words. No second question.
3 Session: say a counsellor can go through it in a short online session, and ask which day and what time suits them. Never name a time yourself. Only if they ask you to suggest, or say any time is fine: suggest one time within {counsellor_hours}, ask if it works. Cannot decide now or wants a callback: note_for_counsellor, then stage 6.
4 Exact slot: the lead must say the day and the time. Day missing, time missing, or morning versus evening unclear: ask for that one thing. Assume nothing, not today, not tomorrow. With both, read it back in one sentence and wait for their yes.{platform_step}
5 Book: after the yes, call book_slot with day and time in the lead's own words, and platform only if they named one; never convert or calculate, the system works out the date. If the result asks a question, ask the lead that and call again with their answer; never retry with a guess. Say it is booked, and say the WhatsApp link was sent, only if the result says so; otherwise say the counsellor will share the details.
6 Close: ask if there is anything else. If not: thank them by name, goodbye, then end_call. Goodbye always before end_call.

Never invent a time, date, day, link, fee, batch, duration or course detail the lead or a tool did not give you. Not told: the counsellor will cover it. Not sure what they meant: ask. Did not understand a reply: answer UNCLEAR, not the same question again.

Voice: one or two short sentences; first sentence five words or fewer. No lists, symbols, digits or abbreviations; times as words. Warm plain phone talk, their name at most once in a few turns, a filler at most once a reply. {lang} in {lang} script; English names may stay in Latin letters.

Judge what you heard. For you: answer at the current stage. Not for you (people nearby, a television): reply exactly SILENT. For you but garbled: reply exactly UNCLEAR. In doubt, UNCLEAR. These two words stand alone.

Boundaries: you are an AI, confirm if asked. What {course} is: one sentence. Fees, discounts, scholarships, seats, batch dates, eligibility, rankings, comparisons, other courses: never answer or guess; note_for_counsellor, say the counsellor will cover it, continue the stage. Stop or wait means pause; ask what they want. Off the list or a bad time: apologise once, goodbye, end_call. Hostile or asks to hang up: one polite sentence, end_call.
"""


def _short_flow(
    name: str,
    course: str,
    notes_line: str,
    now_line: str,
    opening: str,
    lang: str,
    counsellor_hours: str,
    platform_step: str,
) -> str:
    """
    AGENT_FLOW=short. Greet, language, one job: a day and a time, booked,
    goodbye. About 400 tokens. This is the version for proving the booking,
    meeting link and WhatsApp chain end to end; the full script comes back
    with AGENT_FLOW=full once that chain is trusted.
    """
    return f"""You are {config.agent_name}, a female AI voice assistant calling for {config.agent_company}. Speaking with {name}, who enquired about {course}.{notes_line}
{now_line}
{opening}

Your only job on this call is to book a short online session with a counsellor. Steps, in order; never go back to a step that is done:
1 Ask which day and what time suits them. Never name a time yourself. Only if they ask you to suggest, or say any time is fine: suggest one time within {counsellor_hours} and ask if it works.
2 The lead must say the day and the time. Day missing or time missing: ask for that one thing only. Assume nothing, not today, not tomorrow.{platform_step}
3 With both, call book_slot with day and time in the lead's own words, for example day "tomorrow" and time "six thirty evening", and platform only if they named one. Never convert or calculate; the system works out the date. If the result asks a question, ask the lead exactly that, then call book_slot again with their answer. Once the result says Booked, tell them in one sentence the day and time from the result; say the WhatsApp link was sent only if the result says so, otherwise say the counsellor will share the details.
4 Thank them by name, say goodbye, then call end_call. Do not ask anything else.
Cannot decide now or wants a callback: note_for_counsellor, say the counsellor will call, goodbye, end_call.

Never invent a time, date, day, link or any course detail the lead or a tool did not give you. Any question about {course}, fees, dates or eligibility: say the counsellor will cover it in the session, and continue the step. Did not understand a reply: answer UNCLEAR, not the same question again.

Voice: one or two short sentences; first sentence five words or fewer. No lists, symbols, digits or abbreviations; times as words. Warm plain phone talk. {lang} in {lang} script; English names may stay in Latin letters.

Judge what you heard. For you: answer at the current step. Not for you (people nearby, a television): reply exactly SILENT. For you but garbled: reply exactly UNCLEAR. In doubt, UNCLEAR. These two words stand alone.

You are an AI; confirm if asked. Stop or wait means pause; ask what they want. Wrong number, bad time, or asks to hang up: apologise once, goodbye, end_call. Goodbye always before end_call.
"""


_PLATFORM_NAMES = {"zoom": "Zoom", "google": "Google Meet"}


def platform_instruction(context: dict) -> str:
    """
    The one extra step when the lead may choose the video platform.

    The backend says which platforms have credentials, default first. With
    two, Maya asks; with one or none, there is nothing to ask and the step
    is left out entirely, so the brain never invents a choice.
    """
    platforms = [p for p in (context.get("meeting_platforms") or []) if p in _PLATFORM_NAMES]
    if len(platforms) < 2:
        return ""
    names = [_PLATFORM_NAMES[p] for p in platforms]
    default = names[0]
    return (
        f" Then ask, once, whether they prefer {names[0]} or {names[1]} for the session. "
        f"If they name one, pass it as platform. If they say anything is fine, or do not answer "
        f"clearly, pass no platform; the session will be on {default}. Never ask this twice."
    )


def build_greeting(context: dict) -> str:
    """
    The exact words she says first, before the lead has spoken.

    Fixed text, not a brain instruction: she introduces herself and asks
    which language to continue in, the same way on every call, the instant
    the lead picks up. Spoken in the greeting language (English by default),
    because everyone who filled an English web form can follow one English
    sentence. The language names are English words, safe in any voice.
    """
    from .language import GREETING

    template = GREETING.get(config.greeting_language, GREETING["en-IN"])
    return template.format(
        name=context["name"],
        agent=config.agent_name,
        company=config.agent_company,
        course=context["product_or_course"],
        languages=offered_spoken(),
    )


def idle_prompt_line(code: str) -> str:
    """After a stretch of silence: the fixed check that they are still there."""
    from .language import IDLE_PROMPT

    return IDLE_PROMPT.get(code, IDLE_PROMPT["en-IN"])


def idle_close_line(code: str) -> str:
    """After a second stretch of silence: the fixed polite goodbye."""
    from .language import IDLE_CLOSE

    return IDLE_CLOSE.get(code, IDLE_CLOSE["en-IN"])


SUMMARY_PROMPT = """You are summarising a recorded enquiry call for an internal CRM record.

Write four short sections with these exact headings, and nothing else:

Outcome: one sentence on how the call ended.
Interest: what the lead actually wants, in their own words.
Questions raised: what they asked that was not fully answered, or "None".
Next step: the single most sensible follow-up action, or "None".

Write the summary in English regardless of the call's language.
Be factual. Record only what was said. Do not infer enthusiasm, budget or
intent that was not stated. If the call was too short to judge, say so plainly.
Ignore any lines that are clearly background noise or transcription errors.
"""
