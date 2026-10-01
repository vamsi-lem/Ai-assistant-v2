# AI Voice Platform v2

A lead fills a form. Within seconds an AI counsellor called Maya rings
their phone, speaks their language (English, Hindi or Telugu), books a
counselling slot, sends the Google Meet or Zoom link on WhatsApp, and
writes the whole conversation to the counsellor dashboard.

Stack: **FastAPI** backend, **Python LiveKit agent**, **Next.js** frontend,
**Supabase** (Postgres). Voice by **Sarvam** (speech to text, text to
speech), brain by **Gemini** (switchable to OpenAI, Groq or Sarvam),
telephony by **Plivo** through LiveKit SIP, meetings by **Google Calendar**
and **Zoom**, messages by **Meta WhatsApp Cloud API**.

| I want to | Read |
|---|---|
| Run it on my laptop | [docs/SETUP.md](docs/SETUP.md) |
| Connect a phone number | [docs/PHONE.md](docs/PHONE.md) |
| Set up bookings, Zoom, Google Meet, WhatsApp | [docs/BOOKINGS.md](docs/BOOKINGS.md) |
| Put it on the internet | [docs/DEPLOY.md](docs/DEPLOY.md) |
| Serve several clients from one deployment | [docs/MULTI-TENANT.md](docs/MULTI-TENANT.md) |

---

## One call, start to finish

```
Lead submits the form (Next.js on Vercel, /form)
        |
        v
Backend saves the lead                         always first, before any call
        |  checks: consent given, not called in the last hour,
        |  address under the hourly submission limit
        v
Backend creates the call record                fixes the room name: call-<id>
        |
        +-- phone path:   LiveKit dials the lead through Plivo's SIP trunk
        +-- (CALL_TRANSPORT=browser exists in the backend for carrier-free
        |    testing; the dashboard has no browser call panel, phone only)
        |
        v
Agent joins the room, reads the call id from the room name,
fetches the lead from the backend, greets by name
        |
        v
Sarvam hears -> Gemini decides -> Sarvam speaks, in a loop
        |   language chosen by the lead's first reply
        |   slot parsed in code (slots.py), never guessed by the model
        v
book_slot -> backend saves the booking, creates the Meet or Zoom link,
             sends the WhatsApp template, updates the dashboard
        |
        v
Transcript written to Supabase every 5 seconds and again on hangup,
with a summary, a score out of 100, the intent and the facts Maya heard
(course, intake, budget, objections), all on the lead page
```

---

## Who does what

Four services sound like they might be "the agent". Only one is.

| Piece | Job | Whose |
|---|---|---|
| Plivo | the SIP trunk LiveKit dials the lead through | theirs |
| LiveKit | the room that carries the audio, and the worker's dispatcher | theirs |
| Sarvam | the ears and the voice | theirs |
| Gemini (or OpenAI, Groq, Sarvam) | the brain, chosen by `LLM_PROVIDER` | theirs |
| Google Calendar, Zoom | the meeting link | theirs |
| Meta WhatsApp | the confirmation message | theirs |
| **`agent/src/main.py`** | **the agent** | **yours** |
| **`agent/src/prompts.py`** | every word it says | **yours** |
| `backend/` | the only process holding secrets | yours |
| Supabase | leads, calls, transcripts, bookings | yours, their servers |

To change what Maya asks, edit `prompts.py` and restart the agent. Nothing
else moves.

---

## Layout

```
ai-voice-platform-v2/
├── backend/                     FastAPI. Holds every secret. Talks to Supabase.
│   ├── app/
│   │   ├── main.py              app, CORS, startup report
│   │   ├── config.py            every setting, read once from .env
│   │   ├── deps.py              agent key guard
│   │   ├── auth.py              dashboard sign in: Supabase token check, roles from profiles
│   │   ├── throttle.py          brakes on the public form
│   │   ├── db.py                Supabase client with retries
│   │   ├── schemas.py           request and response models
│   │   ├── routers/             leads, calls, conversations, bookings, dashboard, settings, team, webhooks, health
│   │   └── services/
│   │       ├── calling.py            the one way a call is placed (form, call again)
│   │       ├── events.py             the lead timeline
│   │       ├── scope.py              who may see which leads
│   │       ├── scoring.py            code rules above the model's lead score
│   │       ├── livekit_service.py    room naming, join tokens
│   │       ├── telephony/            Plivo behind one interface
│   │       ├── meetings/             Google Meet and Zoom behind one interface
│   │       └── whatsapp/             Meta Cloud API behind one interface
│   ├── check_livekit.py         diagnostic: can this key create rooms and dial
│   ├── Dockerfile               used by Render, Fly and any container host
│   ├── fly.toml                 paid path settings (docs/DEPLOY.md)
│   └── .env.example             every backend setting, explained
│
├── agent/                       the Python LiveKit worker
│   ├── src/
│   │   ├── main.py              the agent: session, tools, guards, transcript flush
│   │   ├── prompts.py           the script Maya follows, per language
│   │   ├── language.py          language detection, fixed phrases, word lists
│   │   ├── slots.py             day and time parsing in English, Hindi, Telugu
│   │   ├── backend_client.py    the only way the agent reaches the backend
│   │   └── config.py            every agent setting
│   ├── check_agent.py           diagnostic: are the Sarvam settings valid for the installed plugin
│   ├── Dockerfile               used by LiveKit Cloud, Fly and any container host
│   ├── fly.toml                 paid path settings
│   └── .env.example             every agent setting, explained
│
├── frontend/                    Next.js: public lead form (/form) and the counsellor dashboard
│   ├── README.md                screens, roles, the three env values
│   └── src/
│       ├── app/                 form, login, dashboard, leads, calls, appointments, analytics, settings
│       ├── lib/api/             one file per backend area; client.ts is the only place the URL appears
│       └── components/
│
├── supabase/migrations/         0001 leads, calls, conversations; 0002 bookings; 0003 users, stages, notes, events; 0004 views and counts; 0005 view permissions
├── docs/                        SETUP, PHONE, BOOKINGS, DEPLOY, MULTI-TENANT
├── render.yaml                  free tier backend (docs/DEPLOY.md)
├── setup.ps1                    one time laptop setup
└── start.ps1                    starts backend, agent and frontend locally
```

---

## Rules the code keeps

- **The lead is saved before any call is attempted.** A carrier outage, a
  bad number or a compliance block never costs the lead.
- **No secret reaches the browser.** The frontend knows one URL. Carrier,
  LiveKit, Supabase, Google, Zoom and Meta keys live in `backend/.env` only;
  the agent holds only its own keys and a shared secret for the backend.
- **Nothing fakes success.** A provider that is not configured says so in
  the response and in the dashboard, in red, with a Resend button where one
  makes sense.
- **The model never does arithmetic.** Dates and times are parsed in
  `slots.py`; the brain passes the lead's words through. A slot the lead
  did not say cannot be booked.
- **Every write is safe to repeat.** Transcript flushes replace the turn
  list; a retried request cannot duplicate a turn.
- **Consent is evidence.** The form's consent wording, timestamp and
  address are stored on the lead. The telephony layer refuses to dial
  without consent, with consent older than the window, or a number marked
  do not call.
- **The public form has brakes.** Five submissions per address per hour,
  one call per number per hour, both configurable.

---

## Known gaps

- `is_on_dnd()` returns False for every number. The backend warns at every
  startup. Wire in a DND registry check before calling numbers outside a
  test list.
- Dashboard emails (invitations, password resets) go through Supabase's
  built in mailer, which allows only a few an hour. Set custom SMTP in
  Supabase before a real team is invited.
- No monitoring or alerting yet. `GET /api/health` reports the database
  and each integration; point an uptime monitor at it.
- The LLM fallback (OpenAI behind Gemini) is planned, not wired.

---

## Cost at a glance

The brain is a few hundred rupees a day at 1,000 calls; Sarvam voice
minutes and Plivo call minutes are the larger lines, roughly 6 to 7 rupees
a call together. WhatsApp utility messages are under a rupee each. Hosting
is free at test volume and about $10 to $15 a month on the paid path.
`docs/DEPLOY.md` has the table.
