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
2. Open **SQL Editor** and run, one after the other, the whole of
   `supabase/migrations/0001_init.sql`, `0002_bookings.sql`,
   `0003_dashboard.sql`, `0004_dashboard_views.sql` and `0005_lock_views.sql`.
3. Go to **Settings → API** and copy three values:
   - Project URL
   - `anon` public key (the frontend uses it to sign users in)
   - the **secret** key, labelled service role

**Check:** the Table Editor shows `leads`, `calls`, `conversations`,
`bookings`, `profiles`, `lead_notes`, `lead_events` and `app_settings`, all
with a green shield icon meaning row level security is on, and no view is
tagged "Unrestricted" (0005 takes care of that).

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
copy .env.example .env.local
npm run dev
```

`.env.local` needs three lines. The first is already right for local work;
the other two come from the Supabase dashboard (Project Settings > API) and
are only used to sign in:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon public key>
```

The anon key is Supabase's public browser key, built to be shipped in a
frontend. The secret key stays in `backend/.env` and never goes here.

**Check:** open <http://localhost:3000/form>. The form renders, and the footer
says `backend ok · db connected`. If the footer says "backend unreachable",
the backend is not running or `CORS_ORIGINS` does not include
`http://localhost:3000`. The dashboard is at <http://localhost:3000> and needs
a login, which the next step creates.

---

## Step 3b. The first dashboard user

Team members are invited from the dashboard's Team tab, but the very first
admin has to be created by hand, once.

1. Supabase → **Authentication → Users → Add user → Create new user**. Enter
   your email and a password, tick **Auto Confirm User**, create.
2. Migration 0003 gave that user a profile with the counsellor role. Make it
   admin in **SQL Editor**:

   ```sql
   update public.profiles set role = 'admin', name = 'Your Name'
   where email = 'you@example.com';
   ```

3. Supabase → **Authentication → URL Configuration**: set **Site URL** to
   `http://localhost:3000` and add `http://localhost:3000/set-password` under
   **Redirect URLs**. Invitation and password reset links land there. When
   the dashboard moves to Vercel, add the Vercel address the same way.
4. Restart the backend (it needs the `PyJWT` package from the updated
   `requirements.txt`: `pip install -r requirements.txt` in `backend`).

**Check:** open <http://localhost:3000>, sign in with that email and password.
The dashboard opens with your name and ADMIN in the top right. Settings →
Team lists you. Invite a second person with your other email address to see
the invitation flow end to end.

> Supabase's built in mailer is meant for testing: it sends only a few
> emails an hour. Before inviting a real team, set custom SMTP under
> **Authentication → Emails** (Resend and Brevo both have free tiers).

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

`docs/DEPLOY.md` is the full guide. The shape:

| Piece | Free path | Paid path |
|---|---|---|
| Frontend | Vercel | Vercel |
| Backend | Render free web service (`render.yaml`) | Fly.io Mumbai (`backend/fly.toml`) |
| Agent | LiveKit Cloud hosted agent (`agent/Dockerfile`) | Fly.io Mumbai (`agent/fly.toml`) |

Two things people get wrong here:

**The agent cannot go on Vercel.** Vercel is serverless: a function runs for
seconds then shuts down. The agent holds a live connection for the length of a
call. It needs an always-on worker, which is what LiveKit Cloud or a Fly
machine provides.

**Update `CORS_ORIGINS` after Vercel gives you a URL.** Skip this and the form
fails silently in the browser with a CORS error that looks exactly like the
backend being down.

---

## Step 8. Phone calls

Wired through LiveKit's SIP bridge: the backend asks LiveKit to dial the
lead through a Plivo SIP trunk, the answered call lands in the room, and
the agent greets once the leg is active. No webhooks, no public URL, works
from a laptop. The full setup, including the exact trunk JSON, is in
`docs/PHONE.md`. In short:

1. Plivo: a Zentrunk outbound trunk with a credential.
2. LiveKit: an outbound trunk pointing at it (`lk sip outbound create`).
3. `backend/.env`: `CALL_TRANSPORT=phone`, `TELEPHONY_ENABLED=true`,
   `PLIVO_FROM_NUMBER`, `LIVEKIT_SIP_TRUNK_ID`.

---

## What the first real run taught us

The code was written without PyPI access, so nothing had been executed until
it ran on a Windows laptop on 18 September 2026. Three things surfaced, all
now fixed. Recorded here so nobody rediscovers them:

1. **Sarvam's LLM refused the plugin.** Every chat request through
   `livekit-plugins-sarvam`'s LLM class returned `400 This endpoint is
   currently in beta and not available`. Speech to text and text to speech
   on the same key work fine. The brain is therefore a separate, switchable
   choice (`LLM_PROVIDER`). Update, 26 September: Sarvam's v1 chat
   completions endpoint is documented as generally available (only their v2
   endpoint is whitelisted per key), so `LLM_PROVIDER=sarvam` now goes
   through the OpenAI client pointed at `https://api.sarvam.ai/v1` rather
   than the plugin's class. `agent/.env.example` has a one line access test.
2. **`anushka` is a `bulbul:v2` speaker.** `bulbul:v3` rejects it at startup
   with the full list of valid names, which is now in `agent/.env.example`.
   Default is `priya`.
3. **`sarvam-105b-conversations` was never verified** on that run and was
   replaced with `sarvam-105b`. Sarvam's current docs list both on the v1
   endpoint and describe the conversations variant as built for voice
   agents, so it is the default again (`SARVAM_LLM_MODEL`). Only relevant
   when `LLM_PROVIDER=sarvam`.

Confirmed working on that run: `sarvam.STTRealtime` with `codemix` and `fast`
(it transcribed Hindi correctly), `sarvam.TTS` with `bulbul:v3`, the
`conversation_item_added` handler, the transcript flush, and the shutdown
hook. The summary call uses `session.llm.chat()` and works with any provider.

Still unverified until the first phone test: the LiveKit outbound trunk to
Plivo (`docs/PHONE.md`). The dial request itself uses only documented
LiveKit API fields, and the agent's wait-for-answer logic reads LiveKit's
own `sip.callStatus` attribute.

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
production (LiveKit Cloud or Fly). If it becomes a nuisance during local testing, run the
agent under WSL2.
