"""
Language control, enforced in code rather than left to the brain.

The first production test showed the brain (a) skipping the language switch
when the lead chose English, so the ears stayed in Hindi mode, and then (b)
switching to Hindi on its own from a single noise transcript, which the prompt
had explicitly forbidden. Prompts are advice. This module is enforcement.

Three jobs:

  detect_choice(text)    Which language did the lead just pick? From the word
                         they said (in any of the offered languages' own words)
                         or, failing that, from the script they replied in.

  looks_foreign(text)    After the language is set, is this transcript mostly
                         in a script the call is not in? Then it is noise, and
                         the brain never sees it.

  sanitise(text, code)   Before the voice speaks, remove any characters the
                         voice for this language cannot read. Sarvam's voice
                         for a language accepts that language's script plus
                         Latin letters, and rejects anything else with a 400,
                         which the lead hears as silence.

Plus FALLBACK, one fixed sentence per language for when the brain's reply had
nothing the voice could say. She apologises and asks them to repeat, in the
right language, every time, deterministically.
"""

from __future__ import annotations

import re
import unicodedata

# Sarvam code -> (English name, Unicode block name of its script)
LANGUAGE_INFO: dict[str, tuple[str, str]] = {
    "hi-IN": ("Hindi", "DEVANAGARI"),
    "en-IN": ("English", "LATIN"),
    "te-IN": ("Telugu", "TELUGU"),
    "ta-IN": ("Tamil", "TAMIL"),
    "kn-IN": ("Kannada", "KANNADA"),
    "ml-IN": ("Malayalam", "MALAYALAM"),
    "mr-IN": ("Marathi", "DEVANAGARI"),
    "bn-IN": ("Bengali", "BENGALI"),
    "gu-IN": ("Gujarati", "GUJARATI"),
    "pa-IN": ("Punjabi", "GURMUKHI"),
    "od-IN": ("Odia", "ORIYA"),
}

# What a lead might SAY to pick a language, in English and in the language
# itself, lowercased. Matched as whole words against the transcript.
CHOICE_WORDS: dict[str, tuple[str, ...]] = {
    "en-IN": ("english", "inglish", "angrezi", "इंग्लिश", "अंग्रेज़ी", "अंग्रेजी", "ఇంగ్లీష్", "ఇంగ్లీషు", "ఆంగ్లం", "ఆంగ్లము"),
    "hi-IN": ("hindi", "हिंदी", "हिन्दी", "హిందీ"),
    "te-IN": ("telugu", "तेलुगु", "तेलुगू", "తెలుగు", "తెలుగులో"),
    "ta-IN": ("tamil", "தமிழ்", "तमिल"),
    "kn-IN": ("kannada", "ಕನ್ನಡ", "कन्नड़", "कन्नड"),
    "ml-IN": ("malayalam", "മലയാളം", "मलयालम"),
    "mr-IN": ("marathi", "मराठी"),
    "bn-IN": ("bengali", "bangla", "বাংলা", "बांग्ला", "बंगाली"),
    "gu-IN": ("gujarati", "ગુજરાતી", "गुजराती"),
    "pa-IN": ("punjabi", "ਪੰਜਾਬੀ", "पंजाबी"),
    "od-IN": ("odia", "oriya", "ଓଡ଼ିଆ", "ओड़िया", "उड़िया"),
}

# Words that mean "I want to change language" in the offered languages. The
# brain's switch tool is only honoured if the lead's last sentence contains
# one of these AND a language name. That is what stops it flipping on noise.
REQUEST_WORDS: tuple[str, ...] = (
    "language", "speak", "talk", "switch", "change", "continue", "please",
    "भाषा", "बोल", "बात", "बोलो", "बोलिए", "करें", "में",
    "మాట్లాడ", "మాట్లాడండి", "మాట్లాడొచ్చు", "భాష", "లో", "చెప్ప",
    "பேச", "மொழி", "ಮಾತನಾಡ", "ಭಾಷೆ", "സംസാരിക്ക", "ഭാഷ",
)

# The fixed sentence spoken when the brain produced nothing the voice can say.
# Feminine forms: Maya is a she.
FALLBACK: dict[str, str] = {
    "en-IN": "Sorry, I did not catch that. Could you say it again?",
    "hi-IN": "माफ़ कीजिए, मैं समझ नहीं पाई। क्या आप दोबारा बता सकते हैं?",
    "te-IN": "క్షమించండి, నాకు అర్థం కాలేదు. దయచేసి మళ్ళీ చెప్పగలరా?",
    "ta-IN": "மன்னிக்கவும், எனக்கு புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳುತ್ತೀರಾ?",
    "ml-IN": "ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?",
    "mr-IN": "माफ करा, मला समजलं नाही. कृपया पुन्हा सांगाल का?",
    "bn-IN": "দুঃখিত, আমি বুঝতে পারিনি। আবার বলবেন কি?",
    "gu-IN": "માફ કરશો, મને સમજાયું નહીં. ફરી કહી શકશો?",
    "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਕੀ ਤੁਸੀਂ ਦੁਬਾਰਾ ਦੱਸ ਸਕਦੇ ਹੋ?",
    "od-IN": "କ୍ଷମା କରନ୍ତୁ, ମୁଁ ବୁଝିପାରିଲି ନାହିଁ। ଦୟାକରି ପୁଣି କହିବେ କି?",
}

# Spoken when the call has been unusable for several turns in a row: she
# leaves politely instead of talking over a television for ten minutes.
NOISY_CLOSE: dict[str, str] = {
    "en-IN": "I am having trouble hearing you clearly. A counsellor will call you at a better time. Thank you, goodbye.",
    "hi-IN": "मुझे आपकी आवाज़ साफ़ सुनाई नहीं दे रही है। हमारे काउंसलर आपको बेहतर समय पर कॉल करेंगे। धन्यवाद, नमस्ते।",
    "te-IN": "మీ మాటలు నాకు స్పష్టంగా వినిపించడం లేదు. మా కౌన్సిలర్ మీకు మంచి సమయంలో కాల్ చేస్తారు. ధన్యవాదాలు, నమస్కారం.",
    "ta-IN": "உங்கள் குரல் எனக்கு தெளிவாக கேட்கவில்லை. எங்கள் ஆலோசகர் உங்களை நல்ல நேரத்தில் அழைப்பார். நன்றி, வணக்கம்.",
    "kn-IN": "ನಿಮ್ಮ ಮಾತು ನನಗೆ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸುತ್ತಿಲ್ಲ. ನಮ್ಮ ಸಲಹೆಗಾರರು ಉತ್ತಮ ಸಮಯದಲ್ಲಿ ನಿಮಗೆ ಕರೆ ಮಾಡುತ್ತಾರೆ. ಧನ್ಯವಾದಗಳು, ನಮಸ್ಕಾರ.",
    "ml-IN": "നിങ്ങളുടെ ശബ്ദം എനിക്ക് വ്യക്തമായി കേൾക്കാൻ കഴിയുന്നില്ല. ഞങ്ങളുടെ കൗൺസിലർ നല്ല സമയത്ത് വിളിക്കും. നന്ദി, നമസ്കാരം.",
    "mr-IN": "मला तुमचा आवाज स्पष्ट ऐकू येत नाही. आमचे समुपदेशक तुम्हाला चांगल्या वेळी कॉल करतील. धन्यवाद, नमस्कार.",
    "bn-IN": "আমি আপনার কথা স্পষ্ট শুনতে পাচ্ছি না। আমাদের কাউন্সেলর আপনাকে ভালো সময়ে ফোন করবেন। ধন্যবাদ, নমস্কার।",
    "gu-IN": "મને તમારો અવાજ સ્પષ્ટ સંભળાતો નથી. અમારા કાઉન્સેલર તમને સારા સમયે કૉલ કરશે. આભાર, નમસ્તે.",
    "pa-IN": "ਮੈਨੂੰ ਤੁਹਾਡੀ ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਸੁਣ ਰਹੀ। ਸਾਡੇ ਕਾਊਂਸਲਰ ਤੁਹਾਨੂੰ ਬਿਹਤਰ ਸਮੇਂ ਕਾਲ ਕਰਨਗੇ। ਧੰਨਵਾਦ, ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ।",
    "od-IN": "ମୁଁ ଆପଣଙ୍କ କଥା ସ୍ପଷ୍ଟ ଶୁଣିପାରୁ ନାହିଁ। ଆମ କାଉନସେଲର ଆପଣଙ୍କୁ ଭଲ ସମୟରେ କଲ କରିବେ। ଧନ୍ୟବାଦ, ନମସ୍କାର।",
}

# The opening line. Fixed text, not the brain: it is spoken the instant the
# lead picks up (no model round trip), it says exactly the same thing on
# every call, and it works when the brain's very first request would fail
# (Gemini refuses a request that has no user message yet, which is exactly
# what a greeting request is). Placeholders: name, agent, company, course,
# languages. Language names are English words in every version because
# every voice can read Latin letters.
GREETING: dict[str, str] = {
    "en-IN": (
        "Hello {name}, this is {agent}, an AI assistant from {company}, calling about "
        "your enquiry regarding {course}. Would you like to continue in {languages}?"
    ),
    "hi-IN": (
        "नमस्ते {name}, मैं {agent} बोल रही हूँ, {company} की AI असिस्टेंट, आपकी {course} "
        "की enquiry के बारे में। आप {languages} में से किस भाषा में बात करना चाहेंगे?"
    ),
    "te-IN": (
        "నమస్కారం {name}, నేను {agent}, {company} నుంచి AI అసిస్టెంట్ ని, మీ {course} "
        "enquiry గురించి కాల్ చేస్తున్నాను. మీరు {languages} లో ఏ భాషలో మాట్లాడాలనుకుంటున్నారు?"
    ),
}

# After a stretch of silence: one fixed check, then a fixed goodbye. Fixed
# for the same reasons as the greeting: instant, identical, brain-proof.
IDLE_PROMPT: dict[str, str] = {
    "en-IN": "Are you still there? Can you hear me?",
    "hi-IN": "क्या आप लाइन पर हैं? क्या आप मुझे सुन पा रहे हैं?",
    "te-IN": "మీరు లైన్ లో ఉన్నారా? నా మాట వినిపిస్తోందా?",
    "ta-IN": "நீங்கள் இன்னும் இருக்கிறீர்களா? என் குரல் கேட்கிறதா?",
    "kn-IN": "ನೀವು ಇನ್ನೂ ಇದ್ದೀರಾ? ನನ್ನ ಮಾತು ಕೇಳಿಸುತ್ತಿದೆಯೇ?",
    "ml-IN": "നിങ്ങൾ അവിടെയുണ്ടോ? എന്റെ ശബ്ദം കേൾക്കുന്നുണ്ടോ?",
    "mr-IN": "तुम्ही अजून लाईनवर आहात का? माझा आवाज ऐकू येतोय का?",
    "bn-IN": "আপনি কি এখনও আছেন? আমার কথা শুনতে পাচ্ছেন?",
    "gu-IN": "તમે હજી લાઇન પર છો? મારો અવાજ સંભળાય છે?",
    "pa-IN": "ਕੀ ਤੁਸੀਂ ਅਜੇ ਲਾਈਨ ਤੇ ਹੋ? ਕੀ ਮੇਰੀ ਆਵਾਜ਼ ਸੁਣ ਰਹੀ ਹੈ?",
    "od-IN": "ଆପଣ ଏବେ ବି ଅଛନ୍ତି କି? ମୋ କଥା ଶୁଣିପାରୁଛନ୍ତି କି?",
}

IDLE_CLOSE: dict[str, str] = {
    "en-IN": "I could not hear you, so a counsellor will call you at a better time. Thank you, goodbye.",
    "hi-IN": "मुझे आपकी आवाज़ नहीं आ रही है, इसलिए हमारे काउंसलर आपको बेहतर समय पर कॉल करेंगे। धन्यवाद, नमस्ते।",
    "te-IN": "మీ మాట వినిపించడం లేదు, అందుకే మా కౌన్సిలర్ మీకు మంచి సమయంలో కాల్ చేస్తారు. ధన్యవాదాలు, నమస్కారం.",
    "ta-IN": "உங்கள் குரல் கேட்கவில்லை, எனவே எங்கள் ஆலோசகர் நல்ல நேரத்தில் அழைப்பார். நன்றி, வணக்கம்.",
    "kn-IN": "ನಿಮ್ಮ ಮಾತು ಕೇಳಿಸಲಿಲ್ಲ, ಆದ್ದರಿಂದ ನಮ್ಮ ಸಲಹೆಗಾರರು ಉತ್ತಮ ಸಮಯದಲ್ಲಿ ಕರೆ ಮಾಡುತ್ತಾರೆ. ಧನ್ಯವಾದಗಳು, ನಮಸ್ಕಾರ.",
    "ml-IN": "നിങ്ങളുടെ ശബ്ദം കേട്ടില്ല, അതിനാൽ ഞങ്ങളുടെ കൗൺസിലർ നല്ല സമയത്ത് വിളിക്കും. നന്ദി, നമസ്കാരം.",
    "mr-IN": "तुमचा आवाज ऐकू आला नाही, म्हणून आमचे समुपदेशक चांगल्या वेळी कॉल करतील. धन्यवाद, नमस्कार.",
    "bn-IN": "আপনার কথা শুনতে পাইনি, তাই আমাদের কাউন্সেলর ভালো সময়ে ফোন করবেন। ধন্যবাদ, নমস্কার।",
    "gu-IN": "તમારો અવાજ સંભળાયો નહીં, એટલે અમારા કાઉન્સેલર સારા સમયે કૉલ કરશે. આભાર, નમસ્તે.",
    "pa-IN": "ਤੁਹਾਡੀ ਆਵਾਜ਼ ਨਹੀਂ ਸੁਣੀ, ਇਸ ਲਈ ਸਾਡੇ ਕਾਊਂਸਲਰ ਬਿਹਤਰ ਸਮੇਂ ਕਾਲ ਕਰਨਗੇ। ਧੰਨਵਾਦ, ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ।",
    "od-IN": "ଆପଣଙ୍କ କଥା ଶୁଣିପାରିଲି ନାହିଁ, ତେଣୁ ଆମ କାଉନସେଲର ଭଲ ସମୟରେ କଲ କରିବେ। ଧନ୍ୟବାଦ, ନମସ୍କାର।",
}

# Two one-word replies the brain can give instead of a sentence:
#   SILENT   what it heard was not addressed to Maya (people nearby, a
#            television, another phone). Nothing is spoken.
#   UNCLEAR  it was for Maya but made no sense. The fixed FALLBACK line for
#            the language is spoken instead of whatever the brain might have
#            improvised, so "did not catch that" sounds the same every time.
# main.py turns both into steps on the unusable-turn ladder.
SILENT = "SILENT"
UNCLEAR = "UNCLEAR"
MARKERS = (SILENT, UNCLEAR)

# Sounds a person makes while thinking, in the scripts the ears produce.
# They are never a language choice and never an interruption worth acting
# on, whatever script they were written in.
FILLERS: frozenset[str] = frozenset({
    "hmm", "hm", "mm", "umm", "um", "uh", "ah", "aa", "haan", "ha", "hu", "huh",
    "ok", "okay", "yes", "no", "hello", "hi", "ya", "yeah", "yep",
    "हम्म", "हम", "हाँ", "हां", "हा", "अं", "ओके", "ठीक", "हेलो", "जी",
    "ఊ", "ఊం", "అ", "హ", "సరే", "ఓకే", "హలో", "అవును", "ఆ",
    # Refusals and "not that": a language choice is never made of these.
    # "नहीं नहीं" was once taken as choosing Hindi.
    "nahi", "nahin", "nai", "no", "not", "नहीं", "नही", "ना", "मत",
    "kadu", "kaadu", "ledu", "వద్దు", "కాదు", "లేదు", "కాదండి",
})


def words(text: str) -> list[str]:
    """
    Words as a person would count them: split on whitespace, strip
    punctuation. Not a regex on letter classes, because the vowel signs of
    Indian scripts are not "letters" to Unicode and a class-based split
    cuts "हम्म" into "हम" and "म".
    """
    out = []
    for raw in text.lower().split():
        w = raw.strip(".,!?;:\"'()[]{}-")
        if w:
            out.append(w)
    return out


def meaningful_words(text: str) -> list[str]:
    return [w for w in words(text) if w not in FILLERS]


def marker_of(text: str) -> str | None:
    """SILENT, UNCLEAR, or None if the text is an ordinary reply."""
    head = text.strip().strip(".!\"'`*").upper()
    return head if head in MARKERS else None


def could_be_marker(text: str) -> bool:
    """Is this partial text still possibly the start of a marker?"""
    head = text.lstrip().lstrip("\"'`*").upper()
    return any(m.startswith(head) for m in MARKERS)


def language_name(code: str) -> str:
    return LANGUAGE_INFO.get(code, ("Hindi", "DEVANAGARI"))[0]


def script_of(code: str) -> str:
    return LANGUAGE_INFO.get(code, ("Hindi", "DEVANAGARI"))[1]


def _char_script(ch: str) -> str | None:
    """
    Unicode block name of a letter, or None for anything that is not a letter.

    Vowel signs and other combining marks (the matras of Indian scripts) count
    as part of their script: they are not letters to Python, but leaving them
    behind when the consonants are removed would send the voice bare marks.
    """
    if not (ch.isalpha() or unicodedata.category(ch).startswith("M")):
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    return name.split(" ")[0]


def letters_by_script(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in text:
        script = _char_script(ch)
        if script:
            counts[script] = counts.get(script, 0) + 1
    return counts


def detect_choice(text: str, offered: list[str]) -> str | None:
    """
    Which offered language did the lead just choose?

    First by name, in any language ("Telugu", "తెలుగు", "तेलुगु"). Then, if
    no name was said, by the script they replied in: a reply written in
    Telugu script IS a Telugu choice. Latin script alone means English.
    A single word is not enough to judge by script ("umm", "hello?") and
    returns None, so she asks again. Returns a Sarvam code, or None.
    """
    named = detect_named_choice(text, offered)
    if named:
        return named

    # By script, only if they said at least three different real words.
    # "Hmm", "okay" and "no no" in any script are not a choice; a real
    # sentence in Hindi or Telugu is.
    real = meaningful_words(text)
    if len(set(real)) < 3:
        return None
    counts = letters_by_script(" ".join(real))
    if not counts:
        return None
    dominant = max(counts, key=counts.get)
    for code in offered:
        if script_of(code) == dominant:
            return code
    return None


def detect_named_choice(text: str, offered: list[str]) -> str | None:
    """A language named in words, in any of the offered languages' own words."""
    lowered = text.lower()
    ws = set(words(text))
    for code in offered:
        for word in CHOICE_WORDS.get(code, ()):
            if word in ws or (len(word) > 4 and word in lowered):
                return code
    return None


def mentions_language_request(text: str) -> bool:
    """
    Does this look like a request to change language?

    Yes if a language is named AND either a request word is present
    ("can we talk in Hindi") or the whole utterance is just the name and a
    word or two ("English", "English please", "Telugu lo"). A language
    name buried in a long sentence about something else is not a request:
    "I studied English literature" must not flip the call.
    """
    lowered = text.lower()
    ws = words(text)
    names = any(
        w in ws or (len(w) > 4 and w in lowered)
        for group in CHOICE_WORDS.values()
        for w in group
    )
    if not names:
        return False
    if len(meaningful_words(text)) <= 3:
        return True
    return any(r in lowered for r in REQUEST_WORDS)


def looks_foreign(text: str, code: str) -> bool:
    """
    True if most of the letters are in a script the call is not in.

    Latin is always allowed: English words inside Hindi or Telugu speech are
    normal. So during an English call, Devanagari noise is foreign; during a
    Telugu call, Devanagari is foreign but Latin is fine.
    """
    counts = letters_by_script(text)
    total = sum(counts.values())
    if total == 0:
        return False
    allowed = {script_of(code), "LATIN"}
    foreign = sum(n for s, n in counts.items() if s not in allowed)
    return foreign / total > 0.5


def sanitise(text: str, code: str) -> str:
    """
    Keep only what the voice for this language can read: its own script,
    Latin letters, digits, punctuation and spaces. Everything else is removed.
    Runs of spaces left behind are collapsed to one. Edges are NOT trimmed:
    the brain's reply arrives in small streamed pieces, and trimming each
    piece would glue words together.
    """
    allowed = {script_of(code), "LATIN"}
    out: list[str] = []
    for ch in text:
        script = _char_script(ch)
        if script is None or script in allowed:
            out.append(ch)
    return re.sub(r"[ \t]{2,}", " ", "".join(out))


def has_speakable_letters(text: str, code: str) -> bool:
    """After sanitising, is there anything left worth saying?"""
    return any(_char_script(ch) in {script_of(code), "LATIN"} for ch in text)


# ---------------------------------------------------------------------------
# Did the lead actually say a time?
#
# The brain once booked a slot nobody had discussed. The fix is not a better
# sentence in the prompt (that was tried) but a check the brain cannot talk
# its way past: book_slot refuses unless the lead's own recent words contain
# something a person says when naming a day or a time. Word stems, so that
# the case endings of Hindi and Telugu ("శుక్రవారానికి", "शाम को") still
# match, in the three scripts the ears produce plus the Latin spellings the
# codemix ears use for Hindi and Telugu words.
# ---------------------------------------------------------------------------

_TIME_STEMS: tuple[str, ...] = (
    # English
    "today", "tomorrow", "tonight", "morning", "afternoon", "evening", "night",
    "noon", "o'clock", "oclock", "am", "pm", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "weekend", "week",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "half", "quarter",
    # Hindi, Latin spelling (codemix ears) and Devanagari
    "aaj", "kal", "parso", "subah", "shaam", "sham", "dopahar", "raat", "baje",
    "somvar", "mangal", "budh", "guru", "shukra", "shani", "ravivar", "itvar",
    "ek", "do", "teen", "char", "paanch", "panch", "chhe", "che", "saat", "aath",
    "nau", "das", "gyarah", "barah", "sadhe", "saade",
    "आज", "कल", "परसों", "सुबह", "शाम", "दोपहर", "रात", "बजे", "सोमवार",
    "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार", "इतवार",
    "एक", "दो", "तीन", "चार", "पांच", "पाँच", "छह", "छः", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "साढ़े", "सवा", "पौने",
    # Telugu, Latin spelling and Telugu script
    "ivala", "ivaala", "repu", "ellundi", "udayam", "udayanne", "madhyahnam",
    "madhyanam", "sayantram", "saayantram", "ratri", "raatri", "ganta",
    "somavaram", "mangalavaram", "budhavaram", "guruvaram", "shukravaram",
    "sanivaram", "adivaram", "okati", "rendu", "moodu", "mudu", "nalugu",
    "aidu", "aaru", "edu", "yedu", "enimidi", "tommidi", "padi", "padakondu",
    "pannendu",
    # Telugu stems are written without the final anusvara so that the
    # inflected forms ("శుక్రవారానికి", "సాయంత్రానికి") still match.
    "ఈరోజు", "ఇవాళ", "ఇవ్వాళ", "రేపు", "ఎల్లుండి", "ఉదయ", "పొద్దున", "మధ్యాహ్న",
    "సాయంత్ర", "రాత్రి", "గంట", "సోమవార", "మంగళవార", "బుధవార", "గురువార",
    "శుక్రవార", "శనివార", "ఆదివార", "ఒకటి", "ఒంటి", "రెండు", "మూడు", "నాలుగు",
    "ఐదు", "అయిదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది", "పది", "పదకొండు",
    "పన్నెండు", "అర",
)

# ---------------------------------------------------------------------------
# Which video platform did the lead ask for?
#
# Same idea as the time guard: the brain may claim the lead chose Zoom, but
# the booking uses that choice only if the lead's own words contain it. In
# the three scripts the ears produce.
# ---------------------------------------------------------------------------

_ZOOM_WORDS = ("zoom", "zum", "जूम", "ज़ूम", "जुम", "జూమ్", "జూం", "జుమ్")
_GOOGLE_WORDS = ("google", "gmeet", "meet", "गूगल", "मीट", "గూగుల్", "మీట్")


def mentions_platform(text: str) -> str | None:
    """'zoom', 'google', or None if neither platform is named."""
    ws = words(text)
    lowered = text.lower()
    zoom = any(w in ws for w in _ZOOM_WORDS) or "zoom" in lowered
    google = any(w in ws for w in _GOOGLE_WORDS) or "google" in lowered
    if zoom and not google:
        return "zoom"
    if google and not zoom:
        return "google"
    return None


# Short stems match only as whole words, so "am" does not fire on "amount"
# and "do" does not fire on "doubt". Longer stems may carry a case ending.
_SHORT_STEM = 4


def mentions_time(text: str) -> bool:
    """
    True if these words, said by the lead, name a day or a time of day: a
    digit, a weekday, today or tomorrow, morning or evening, a number word,
    in English, Hindi or Telugu. False for "yes", "okay", "fine with me" and
    any other sentence that agrees without saying when.
    """
    if re.search(r"\d", text):
        return True
    for w in words(text):
        for stem in _TIME_STEMS:
            if len(stem) < _SHORT_STEM:
                if w == stem:
                    return True
            elif w.startswith(stem):
                return True
    return False
