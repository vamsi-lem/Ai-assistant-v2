# AI Voice Platform v2

Lead fills a form, an AI assistant calls them, the conversation is stored.

Rebuild of v1 on a new stack: **Supabase** instead of MongoDB, **Python**
instead of TypeScript, **Sarvam AI** instead of Deepgram and ElevenLabs, and
an Indian carrier instead of Twilio.

Start with **[docs/SETUP.md](docs/SETUP.md)**. It is ordered and each step has
one thing to check before the next.

---

## Who does what

The single most confusing thing about this architecture is that four different
services all sound like they might be "the agent". Only one is.

| Piece | Job | Whose |
|---|---|---|
| **Plivo** | dials the lead's mobile, then goes silent | theirs |
| **LiveKit** | the room that carries the audio | theirs |
| **Sarvam** | the ears and the voice (speech to text, text to speech) | theirs |
| **OpenAI** (or Groq) | the brain. Sarvam's LLM is a closed beta, so this is switchable via `LLM_PROVIDER` | theirs |
| **`agent/src/main.py`** | **the agent** | **yours** |
| **`agent/src/prompts.py`** | every word it says | **yours** |
| **Supabase** | leads, calls, transcripts | yours, their servers |

LiveKit is the room, not the agent. Sarvam is the models, not the agent. The
agent is your code. If you want to change what it asks, edit `prompts.py` and
restart the agent. Nothing else moves.

---

## One call, start to finish

```
Lead submits form (React, Vercel)
        |
        v
Backend saves the lead                        <- always first, before any call
        |
        v
Backend creates the call record               <- fixes the room name: call-<id>
        |
        +--- browser path: mints a LiveKit token, the browser joins the room
        |
        +--- phone path:   asks Plivo to dial, Plivo bridges the answered
                           call into the room, then plays no further part
        |
        v
Agent joins the room, reads the call id from the room name,
fetches the lead from the backend, and talks
        |
        v
Sarvam hears -> decides -> speaks, in a loop
        |
        v
Transcript written to Supabase every 5 seconds, and again on hangup
```

---

## Layout

```
ai-voice-platform-v2/
├── supabase/migrations/     the three tables, with row level security on
├── backend/                 FastAPI. The only process holding secrets.
│   └── app/
│       ├── routers/         one module per resource
│       └── services/
│           ├── livekit_service.py    room naming and join tokens
│           └── telephony/            carrier behind one interface
├── agent/                   the Python LiveKit worker, running on Sarvam
│   └── src/
│       ├── main.py          the agent
│       └── prompts.py       everything it says
├── frontend/                React + Vite. Lead form and call panel.
└── docs/SETUP.md            run order and verification
```

---

## Decisions worth knowing

**The lead is saved before any call is attempted.** A carrier outage, a bad
number or a compliance block must never cost you the lead. This ordering is
the one rule in `routers/leads.py` that must not be rearranged.

**Browser transport is the default.** It needs no carrier, no phone number and
costs nothing per minute, so the whole pipeline can be built and tested before
any telephony paperwork exists. `CALL_TRANSPORT=phone` switches it.

**The carrier layer is real code that stays dormant.** With no credentials,
a phone-path request saves the lead and returns a clear "Plivo is not
configured, missing X and Y" reason. It never fakes a success, because a lead
showing as "calling" when nothing dialled is worse than a visible error.

**Transcripts are replaced, not appended.** The agent posts the complete turn
list on every flush. A retried or duplicated write can therefore never produce
duplicate turns.

**The agent holds no database credentials.** It is handed a room named
`call-<id>`, recovers the id, and asks the backend for everything else. That
keeps the Supabase secret key in one process, and it is why the same agent code
serves a browser participant today and a phone participant later unchanged.

**Row level security is on with no policies.** The anon key can read and write
nothing. Every write goes through the backend using the secret key. If you
later add a client dashboard, add explicit policies then; do not turn RLS off.

---

## Compliance, built in rather than bolted on

India prohibits cold calling and requires explicit digital consent before a
commercial call. Two things enforce that here:

- The form's consent checkbox is **required**, and its exact wording, the
  timestamp and the IP are stored against the lead as evidence.
- `services/telephony/service.py` refuses to dial a lead with no consent,
  with consent older than seven days, or marked `do_not_call`.

One gap, flagged rather than hidden: the do-not-call check
(`is_on_dnd`) is not implemented and currently returns False for every number.
The backend warns about this at every startup. Wire it in before calling
anyone outside a test list. Five complaints from five recipients within ten
days bars your number for fifteen days.

---

## Costs at a glance

About **₹6.34** per three minute call, plus roughly **₹1,500 a month** fixed at
pilot volume. Sarvam's voice is about two thirds of the per-call cost, which is
why the prompt keeps replies to one or two sentences.

The phone path adds a large fixed cost: LiveKit region pinning is required by
law for Indian numbers and only sold on their Scale plan at $500 a month.
Build and prove the browser path first.

Full breakdown, with sources, in `ai-voice-platform-vendors-and-costs.pdf`.

---

## Status

| | |
|---|---|
| Supabase schema | written |
| Backend, six endpoints | written |
| Frontend, form and call panel | written |
| Agent on Sarvam | written |
| Plivo layer | written, dormant until configured |
| DND check | **not implemented**, warned at startup |
| Anything executed | **no** — PyPI was unreachable where this was written |

Nothing here has been run. See the end of `docs/SETUP.md` for the four
specific things to verify first.
