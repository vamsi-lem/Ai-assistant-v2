# Setup and verification

Run in this order. Each step has one thing to check before you move on. If a
check fails, stop there and tell me what you saw, because every later step
depends on it.

---

## Step 0. What you need before starting

| Account | Cost | Where |
|---|---|---|
| Supabase | free | supabase.com |
| Sarvam AI | free, about 100 rupees credit | dashboard.sarvam.ai |
| LiveKit | free Build plan | you already have this |
| Plivo | ₹2,000 refundable | only for the phone path, later |

Nothing in steps 1 to 6 needs a phone number, a carrier, or any money.

---

## Step 1. Supabase project and tables

1. Create a project at **supabase.com**. Region **Mumbai (ap-south-1)**.
2. Open **SQL Editor**, paste the whole of `supabase/migrations/0001_init.sql`,
   and run it.
3. Go to **Settings → API** and copy three values:
   - Project URL
   - `anon` public key (the frontend never actually needs it in this build, but
     keep it)
   - the **secret** key, labelled service role

**Check:** the Table Editor shows `leads`, `calls` and `conversations`, all
three with a green shield icon meaning row level security is on.

> The shield matters. Those tables deny the anon key everything, so a leaked
> frontend key cannot read a single lead. Only the backend and the agent, using
> the secret key, can touch them.

---

## Step 2. Backend

```powershell
cd "D:\Lemniscate Growth\ai-voice-platform-v2\backend"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and fill in:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SECRET_KEY=<the secret key from step 1>
LIVEKIT_URL=wss://ai-4q4g4wio.livekit.cloud
LIVEKIT_API_KEY=<yours>
LIVEKIT_API_SECRET=<yours>
AGENT_API_KEY=<generate it, see below>
CALL_TRANSPORT=browser
```

Generate the agent key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save that value. It goes in **both** `backend/.env` and `agent/.env`, identical.

Run it:

```powershell
uvicorn app.main:app --reload --port 8000
```

**Check:** open <http://localhost:8000/api/health>. You want:

```json
{
  "status": "ok",
  "database": "connected",
  "transport": "browser (WebRTC). No carrier involved, no per-minute cost.",
  "agent_auth": "configured"
}
```

`"database": "connected"` is the important one. Anything else means the
Supabase URL or secret key is wrong.

You will also see a warning in the log about DND checking not being
implemented. That is correct and deliberate. It matters before you call real
strangers, not before you test.

---

## Step 3. Frontend

In a second terminal:

```powershell
cd "D:\Lemniscate Growth\ai-voice-platform-v2\frontend"
npm install
copy .env.example .env
npm run dev
```

`.env` needs one line, and the default is already right for local work:

```
VITE_API_BASE_URL=http://localhost:8000/api
```

**Check:** open <http://localhost:5173>. The form renders, and the footer says
`backend ok · db connected`. If the footer says "backend unreachable", the
backend is not running or `CORS_ORIGINS` does not include
`http://localhost:5173`.

---

## Step 4. Prove the database write, before any voice

Fill the form with your own details, tick the consent box, and submit.

**Check, in Supabase Table Editor:**

- `leads` has one new row, with `consent_given = true` and a `consent_at`
  timestamp
- `calls` has one new row, `transport = browser`, `room_name = call-<the call id>`

At this point the lead pipeline works end to end. The agent is not running yet,
so the call panel will sit there with zero turns. That is expected.

> Now try it again **without** ticking consent. The lead should save and the
> page should say "Saved, but not called". That is the compliance gate doing its
> job: no consent, no call.

---

## Step 5. Agent

Third terminal:

```powershell
cd "D:\Lemniscate Growth\ai-voice-platform-v2\agent"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill in `agent/.env`:

```
LIVEKIT_URL=wss://ai-4q4g4wio.livekit.cloud
LIVEKIT_API_KEY=<same as backend>
LIVEKIT_API_SECRET=<same as backend>
BACKEND_BASE_URL=http://localhost:8000/api
AGENT_API_KEY=<the SAME value as backend/.env>
SARVAM_API_KEY=<from dashboard.sarvam.ai>
```

Download the voice detection model once:

```powershell
python -m src.main download-files
```

Then run:

```powershell
python -m src.main dev
```

**Check:** the log shows `Silero VAD loaded` and a line containing
`registered worker`. That means it has connected to LiveKit and is waiting for
a room.

If you see `Missing in agent/.env`, it tells you exactly which variable.

---

## Step 6. The real test

With all three running, submit the form again.

Expected sequence:

1. The page moves to the call panel
2. Your browser asks for microphone permission. Allow it.
3. You may see "One more tap" with a **Turn on sound** button. Click it. This
   is the browser blocking autoplay, not a bug.
4. Maya greets you by name and says she is an AI assistant
5. Talk to her. Try Hindi, English, or a mix.
6. Hang up

**Check:**

- The agent log ends with `Call <id> ended, N turn(s) stored`
- In Supabase, `conversations` has a row for that call
- Open its `messages` column. You should see **both** roles: `assistant` lines
  and `user` lines
- `calls.status` is `completed`, `leads.status` is `contacted`

If both roles are there, the whole pipeline works and steps 1 to 6 are signed
off.

---

## Step 7. Deploy

| Piece | Platform | Root directory | Notes |
|---|---|---|---|
| Frontend | Vercel | `frontend` | framework preset Vite |
| Backend | Railway | `backend` | start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Agent | Railway | `agent` | start `python -m src.main start`, no domain |

Two things people get wrong here:

**The agent cannot go on Vercel.** Vercel is serverless: a function runs for
seconds then shuts down. The agent holds a live connection for the length of a
call. It needs an always-on Railway service.

**Update `CORS_ORIGINS` after Vercel gives you a URL.** Skip this and the form
fails silently in the browser with a CORS error that looks exactly like the
backend being down.

Also note the agent's build command on Railway must include the model download:

```
pip install -r requirements.txt && python -m src.main download-files
```

Without it the agent tries to fetch the voice detection model mid-call.

---

## Step 8. Phone calls, later

Blocked on two things that are not code:

1. **A Plivo account** with an Indian landline-series number (080 or 022, not
   a mobile, not 140). About an hour, needs your GST certificate.
2. **LiveKit India region pinning.** Required by law for Indian numbers and
   only available on their Scale plan at $500 a month. Email their sales team
   before assuming this is affordable.

When both are ready, set in `backend/.env`:

```
CALL_TRANSPORT=phone
TELEPHONY_ENABLED=true
PLIVO_AUTH_ID=...
PLIVO_AUTH_TOKEN=...
PLIVO_FROM_NUMBER=+9180xxxxxxxx
LIVEKIT_SIP_URI=your-project.sip.livekit.cloud
PUBLIC_BASE_URL=https://your-backend.up.railway.app
```

No code changes. The Plivo path is already written and sits dormant until
those values exist.

**One thing to verify before the first live phone call:** the SIP element name
in `backend/app/services/telephony/plivo_provider.py`, in `answer_xml()`. I
wrote `<Dial><User>sip:...</User></Dial>` from Plivo's documentation but could
not test it. Check it against Plivo's own LiveKit integration guide. A wrong
element name shows up as a call that connects and then silently drops, which
is a miserable thing to debug.

---

## What the first real run taught us

The code was written without PyPI access, so nothing had been executed until
it ran on a Windows laptop on 18 September 2026. Three things surfaced, all
now fixed. Recorded here so nobody rediscovers them:

1. **Sarvam's LLM is a closed beta.** Every chat request from an ordinary
   account returns `400 This endpoint is currently in beta and not available`.
   Speech to text and text to speech on the same key work fine. The brain is
   therefore a separate, switchable choice (`LLM_PROVIDER`), defaulting to
   OpenAI. Sarvam remains an option for when they grant access.
2. **`anushka` is a `bulbul:v2` speaker.** `bulbul:v3` rejects it at startup
   with the full list of valid names, which is now in `agent/.env.example`.
   Default is `priya`.
3. **`sarvam-105b-conversations` was never verified.** Replaced with the
   plugin's own default, `sarvam-105b`. Only relevant when `LLM_PROVIDER=sarvam`.

Confirmed working on that run: `sarvam.STTRealtime` with `codemix` and `fast`
(it transcribed Hindi correctly), `sarvam.TTS` with `bulbul:v3`, the
`conversation_item_added` handler, the transcript flush, and the shutdown
hook. The summary call uses `session.llm.chat()` and works with any provider.

Still unverified: **the Plivo SIP element**, as above. It cannot be tested
without a bought number.

### Known Windows issue

An intermittent native crash inside LiveKit's own audio library:

```
Assertion failed!  livekit_ffi.dll  soxr-sys/src/fft4g_cache.h
Expression: LSX_FFT_BR == NULL
```

This is a thread-safety race in the resampler that ships inside LiveKit's
Rust SDK, triggered when the input and output resamplers initialise at the
same moment. Not in this codebase. Click **Ignore** and the call usually
continues. It does not occur on Linux, which is where the agent runs in
production (Railway). If it becomes a nuisance during local testing, run the
agent under WSL2.
