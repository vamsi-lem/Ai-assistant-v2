"""
Turning "tomorrow at half past six" into an exact moment.

The brain does not do this. On a real call it was asked to work out the
ISO timestamp for "Wednesday at six thirty" and produced 5 March, six
months in the past, four times in a row, while the current date sat in
its instructions. Small fast models are good at copying words and bad at
calendar arithmetic. So the brain now passes the lead's words for the day
and the time, and this file does the arithmetic, the same way every time.

Understood, in English, Hindi and Telugu (own script and Latin spelling):

  day    today, tomorrow, day after tomorrow, a weekday name, a date like
         "22 september", "september 22", "22nd", or just "22"
  time   6, 6:30, 6.30, 630, half past six, quarter past six, six thirty,
         saade chhe, ఆరున్నర, with am, pm, morning, afternoon, evening,
         night in any of the three languages, or without: then the hour
         is placed inside the counsellor's working day

Everything comes back as a datetime in the booking timezone, or a short
sentence saying what is missing, written for the brain to act on.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .language import words

# ---------------------------------------------------------------------------
# Vocabulary. Stems, so that case endings still match ("शुक्रवार को",
# "శుక్రవారానికి"). Latin spellings are what Sarvam's codemix ears write
# for Hindi and Telugu words spoken inside an English sentence.
# ---------------------------------------------------------------------------

_TODAY = ("today", "tonight", "aaj", "आज", "ఈరోజు", "ఇవాళ", "ఇవ్వాళ", "ivala", "ivaala", "eeroju")
_TOMORROW = ("tomorrow", "kal", "कल", "రేపు", "repu", "rep")
_DAY_AFTER = ("parso", "परसों", "ఎల్లుండి", "ellundi", "elundi")

# 0 = Monday, as datetime.weekday() counts.
_WEEKDAYS: dict[int, tuple[str, ...]] = {
    0: ("monday", "mon", "somvar", "somwar", "सोमवार", "సోమవార", "somavaram", "somavar"),
    1: ("tuesday", "tue", "tues", "mangalvar", "mangalwar", "मंगलवार", "మంగళవార", "mangalavaram"),
    2: ("wednesday", "wed", "budhvar", "budhwar", "बुधवार", "బుధవార", "budhavaram"),
    3: ("thursday", "thu", "thur", "thurs", "guruvar", "guruwar", "गुरुवार", "गुरूवार", "గురువార", "guruvaram"),
    4: ("friday", "fri", "shukravar", "shukrawar", "शुक्रवार", "శుక్రవార", "shukravaram", "sukravaram"),
    5: ("saturday", "sat", "shanivar", "shaniwar", "शनिवार", "శనివార", "sanivaram", "shanivaram"),
    6: ("sunday", "sun", "ravivar", "raviwar", "itvar", "रविवार", "इतवार", "ఆదివార", "adivaram", "aadivaram"),
}

_MONTHS: dict[int, tuple[str, ...]] = {
    1: ("january", "jan", "जनवरी", "జనవరి"),
    2: ("february", "feb", "फ़रवरी", "फरवरी", "ఫిబ్రవరి"),
    3: ("march", "mar", "मार्च", "మార్చి"),
    4: ("april", "apr", "अप्रैल", "ఏప్రిల్"),
    5: ("may", "मई", "మే"),
    6: ("june", "jun", "जून", "జూన్"),
    7: ("july", "jul", "जुलाई", "జులై", "జూలై"),
    8: ("august", "aug", "अगस्त", "ఆగస్టు", "ఆగస్ట్"),
    9: ("september", "sept", "sep", "सितंबर", "सितम्बर", "సెప్టెంబర్", "సెప్టెంబరు"),
    10: ("october", "oct", "अक्टूबर", "अक्तूबर", "అక్టోబర్", "అక్టోబరు"),
    11: ("november", "nov", "नवंबर", "नवम्बर", "నవంబర్", "నవంబరు"),
    12: ("december", "dec", "दिसंबर", "दिसम्बर", "డిసెంబర్", "డిసెంబరు"),
}

_NUMBER_WORDS: dict[str, int] = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
    "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
    "thirtieth": 30, "twenty": 20, "thirty": 30, "fifteen": 15, "forty": 40, "fifty": 50,
    # Hindi, Latin and Devanagari
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "che": 6, "chah": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9,
    "das": 10, "dus": 10, "gyarah": 11, "gyaarah": 11, "barah": 12, "baarah": 12,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12,
    # Telugu, Latin and Telugu script
    "okati": 1, "rendu": 2, "moodu": 3, "mudu": 3, "nalugu": 4, "aidu": 5, "ayidu": 5,
    "aaru": 6, "aru": 6, "edu": 7, "yedu": 7, "enimidi": 8, "tommidi": 9, "padi": 10,
    "padakondu": 11, "pannendu": 12, "okka": 1, "onti": 1,
    "ఒకటి": 1, "ఒంటి": 1, "ఒక్క": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "అయిదు": 5,
    "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10, "పదకొండు": 11, "పన్నెండు": 12,
}

# Hindi "saade chhe" and Telugu "aarunnara" both mean half past six; the
# half is glued to the number in Telugu, so those forms are listed whole.
_HALF_WORDS = ("half", "saade", "sadhe", "sade", "साढ़े", "साढे", "ara", "అర", "nnara", "న్నర")
_QUARTER_PAST = ("quarter", "sava", "sawa", "सवा", "ముప్పావు")
_QUARTER_TO = ("paune", "पौने")
_TELUGU_HALF: dict[str, int] = {
    "okatinnara": 1, "ఒకటిన్నర": 1, "rendunnara": 2, "రెండున్నర": 2, "moodunnara": 3, "మూడున్నర": 3,
    "nalugunnara": 4, "నాలుగున్నర": 4, "aidunnara": 5, "ఐదున్నర": 5, "aarunnara": 6, "ఆరున్నర": 6,
    "edunnara": 7, "ఏడున్నర": 7, "enimidinnara": 8, "ఎనిమిదిన్నర": 8, "tommidinnara": 9, "తొమ్మిదిన్నర": 9,
    "padinnara": 10, "పదిన్నర": 10, "padakondunnara": 11, "పదకొండున్నర": 11, "pannendunnara": 12, "పన్నెండున్నర": 12,
}

_AM_WORDS = ("am", "a.m", "morning", "subah", "savere", "सुबह", "सवेरे", "udayam", "udayanne", "podduna", "ఉదయ", "పొద్దున", "ప్రొద్దున")
_PM_WORDS = (
    "pm", "p.m", "afternoon", "evening", "night", "noon", "dopahar", "shaam", "sham", "raat",
    "दोपहर", "शाम", "रात", "madhyahnam", "madhyanam", "sayantram", "saayantram", "ratri", "raatri",
    "మధ్యాహ్న", "సాయంత్ర", "రాత్రి",
)

_DIGIT_MAP = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")


def _has(ws: list[str], stems: tuple[str, ...]) -> bool:
    for w in ws:
        for s in stems:
            if len(s) <= 3:
                if w == s:
                    return True
            elif w.startswith(s):
                return True
    return False


def _norm(text: str) -> str:
    return text.translate(_DIGIT_MAP).lower().replace("o'clock", " ").replace("oclock", " ")


# ---------------------------------------------------------------------------
# Day
# ---------------------------------------------------------------------------


def resolve_day(text: str, now: datetime) -> tuple[datetime | None, str | None]:
    """
    The calendar day the lead meant, at midnight in now's timezone, or a
    sentence saying what was missing. Weekday names mean the NEXT such day
    (today counts if it is still today; the time check later moves it on).
    """
    text = _norm(text)
    ws = words(text)
    if not ws:
        return None, "Ask which day suits them."

    base = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if _has(ws, _DAY_AFTER) or (_has(ws, _TOMORROW) and "after" in ws):
        return base + timedelta(days=2), None
    if _has(ws, _TOMORROW):
        return base + timedelta(days=1), None
    if _has(ws, _TODAY):
        return base, None

    for weekday, stems in _WEEKDAYS.items():
        if _has(ws, stems):
            ahead = (weekday - base.weekday()) % 7
            return base + timedelta(days=ahead), None

    # A date: "22 september", "september 22nd", "22nd", "the 22nd", "22".
    month = None
    for number, stems in _MONTHS.items():
        if _has(ws, stems):
            month = number
            break
    day = None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", text)
    if m:
        day = int(m.group(1))
    else:
        for w in ws:
            if w in _NUMBER_WORDS and _NUMBER_WORDS[w] <= 31:
                day = _NUMBER_WORDS[w]
                break
    if day and 1 <= day <= 31:
        year = base.year
        if month is None:
            month = base.month
            if day < base.day:
                month += 1
        if month < base.month or (month == base.month and day < base.day):
            year += 1
        if month > 12:
            month, year = 1, year + 1
        try:
            return base.replace(year=year, month=month, day=day), None
        except ValueError:
            return None, "That date does not exist. Ask which day they meant."

    return None, "Ask which day suits them, for example tomorrow or a weekday."


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def resolve_time(text: str, *, work_start: int, work_end: int) -> tuple[tuple[int, int] | None, str | None]:
    """
    (hour, minute) in 24 hour form, or a sentence saying what was missing.

    With no am, pm, morning or evening word, the hour is placed inside the
    counsellor's working day: "six" becomes 6 pm when the day runs ten to
    seven, "ten" becomes 10 am. Only an hour that fits neither way is sent
    back as a question.
    """
    text = _norm(text)
    ws = words(text)
    if not ws:
        return None, "Ask what time suits them."

    hour: int | None = None
    minute = 0

    # 6:30, 6.30, 18:30, 630, 1830
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(\d{3,4})\b", text)
        if m and int(m.group(1)[-2:]) < 60 and int(m.group(1)[:-2]) <= 24:
            hour, minute = int(m.group(1)[:-2]), int(m.group(1)[-2:])
        else:
            m = re.search(r"\b(\d{1,2})\b", text)
            if m:
                hour = int(m.group(1))

    if hour is None:
        for w in ws:
            if w in _TELUGU_HALF:
                hour, minute = _TELUGU_HALF[w], 30
                break
        if hour is None:
            for w in ws:
                if w in _NUMBER_WORDS and _NUMBER_WORDS[w] <= 24:
                    hour = _NUMBER_WORDS[w]
                    break

    if hour is None:
        return None, "Ask what time suits them, for example six in the evening."

    if minute == 0:
        if _has(ws, _HALF_WORDS):
            minute = 30
        elif _has(ws, _QUARTER_TO):
            hour, minute = hour - 1, 45
        elif _has(ws, _QUARTER_PAST):
            minute = 15
        else:
            # "six thirty", "six fifteen", "chhe bees"
            for w in ws:
                if w in ("thirty", "tees", "तीस", "muppai", "ముప్పై"):
                    minute = 30
                elif w in ("fifteen", "pandrah", "पंद्रह", "padihenu", "పదిహేను"):
                    minute = 15
                elif w in ("forty", "chalis", "चालीस", "nalabhai", "నలభై"):
                    minute = 45 if "five" in ws or "paanch" in ws or "aidu" in ws else 40
    if not (0 <= minute < 60):
        return None, "Ask what time suits them."

    is_pm = _has(ws, _PM_WORDS)
    is_am = _has(ws, _AM_WORDS) and not is_pm

    if hour > 24:
        return None, "Ask what time suits them."
    if hour == 24:
        hour = 0

    if hour >= 13:
        pass  # already 24 hour
    elif is_pm:
        hour = hour % 12 + 12
    elif is_am:
        hour = hour % 12
    else:
        # No am or pm. Choose the reading inside working hours; if both fit
        # (rare), prefer the afternoon, which is when leads usually are free.
        pm = hour % 12 + 12
        am = hour % 12
        if work_start <= pm < work_end:
            hour = pm
        elif work_start <= am < work_end:
            hour = am
        else:
            return None, "Ask whether they mean morning or evening."

    return (hour, minute), None


# ---------------------------------------------------------------------------
# Both together
# ---------------------------------------------------------------------------


def resolve_slot(
    day_text: str,
    time_text: str,
    *,
    now: datetime,
    work_start: int = 10,
    work_end: int = 19,
    min_notice_minutes: int = 30,
) -> tuple[datetime | None, str | None]:
    """
    The exact moment, or one sentence telling the brain what to ask.

    A weekday that has already passed today moves to next week; "today" at
    a time already gone is refused. Nothing is ever invented: if a piece is
    missing the answer is a question, never a guess.
    """
    day, err = resolve_day(day_text, now)
    if err:
        return None, err
    hm, err = resolve_time(time_text, work_start=work_start, work_end=work_end)
    if err:
        return None, err
    assert day is not None and hm is not None

    when = day.replace(hour=hm[0], minute=hm[1])
    if when < now + timedelta(minutes=min_notice_minutes):
        ws = words(_norm(day_text))
        if _has(ws, _TODAY) or not any(_has(ws, s) for s in _WEEKDAYS.values()):
            return None, "That time has already passed. Ask for a later time today, or another day."
        when += timedelta(days=7)
    return when, None
