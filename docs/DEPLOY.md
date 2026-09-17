# Deploying

Three services from one repository. About an hour, mostly pasting values you
already have in your local `.env` files.

| Piece | Goes to | Root directory | Needs a public URL |
|---|---|---|---|
| `backend/` | Railway | `backend` | yes |
| `agent/` | Railway | `agent` | no |
| `frontend/` | Vercel | `frontend` | yes |
| `supabase/` | already deployed | | |

Do them in this order. Each step gives you a URL the next one needs.

---

## 0. Push to GitHub

From the project folder:

```powershell
cd "D:\Lemniscate Growth\ai-voice-platform-v2"
git init
git add .
git commit -m "Phase 1: browser calls working end to end"
```

Create an empty repository on GitHub (private), then:

```powershell
git remote add origin https://github.com/YOUR-USER/ai-voice-platform-v2.git
git branch -M main
git push -u origin main
```

Before you push, confirm no secret is in the commit:

```powershell
git ls-files | Select-String "\.env$"
```

That must print nothing. `.gitignore` excludes every `.env`, so it will,
but check anyway. The `.env.example` files are meant to be committed.

---

## 1. Backend on Railway

1. **railway.app**, sign in with GitHub, **New Project**, **Deploy from GitHub
   repo**, pick the repository.
2. Railway creates one service. Open it, go to **Settings**.
3. **Root Directory**: `backend`. Railway will find the Dockerfile there.
4. **Networking**, click **Generate Domain**. Copy it. This is your backend
   URL, something like `https://backend-production-xxxx.up.railway.app`.
5. **Variables**, paste these. Every value except the last three is the same
   as your local `backend\.env`:

```
APP_ENV=production
SUPABASE_URL=
SUPABASE_SECRET_KEY=
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
AGENT_API_KEY=
CALL_TRANSPORT=browser
TELEPHONY_ENABLED=false
TELEPHONY_PROVIDER=plivo
DND_CHECK_ENABLED=true
CONSENT_WINDOW_DAYS=7

PUBLIC_BASE_URL=https://the-domain-from-step-4
CORS_ORIGINS=http://localhost:5173
```

   Leave `PORT` out. Railway sets it. `CORS_ORIGINS` gets the Vercel URL added
   in step 3, you do not have it yet.

6. Railway deploys on save. Wait for the build to go green, then open
   `https://your-backend-domain/api/health`. You want `"database": "connected"`.

---

## 2. Agent on Railway

Same project, second service.

1. In the project, **New**, **GitHub Repo**, the same repository.
2. **Settings**, **Root Directory**: `agent`.
3. **Networking**: do NOT generate a domain. The agent dials out to LiveKit;
   nothing dials in to it.
4. **Variables**:

```
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
AGENT_API_KEY=
SARVAM_API_KEY=

LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b

SARVAM_STT_LANGUAGE=hi-IN
SARVAM_STT_MODE=codemix
SARVAM_STT_STREAM_TYPE=fast
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_LANGUAGE=hi-IN
SARVAM_TTS_SPEAKER=priya
SARVAM_TTS_PACE=1.0

AGENT_NAME=Maya
AGENT_COMPANY=Lemniscate Growth
AGENT_FLUSH_INTERVAL_SECONDS=5
AGENT_GENERATE_SUMMARY=true
AGENT_ROOM_PREFIX=call-

BACKEND_BASE_URL=https://your-backend-domain/api
```

   `BACKEND_BASE_URL` is the step 1 domain plus `/api`. `AGENT_API_KEY` must
   be identical to the backend's, character for character.

5. The first build is slow, five to ten minutes. It installs the voice stack
   and downloads the model files into the image. Later builds are faster.
6. Open the service's **Logs**. You want `registered worker` with
   `"region": "India South"`. That line means the agent is live.

**Stop the local agent** now. Two agents on the same LiveKit project will
both accept calls and you will not know which one answered. Close its window
on your laptop, or run `Get-Process python | Stop-Process -Force`.

---

## 3. Frontend on Vercel

1. **vercel.com**, sign in with GitHub, **Add New**, **Project**, import the
   repository.
2. **Root Directory**: click Edit, choose `frontend`.
3. Framework preset should auto-detect **Vite**. Build command
   `npm run build`, output directory `dist`. Leave as detected.
4. **Environment Variables**, one entry:

```
VITE_API_BASE_URL=https://your-backend-domain/api
```

5. **Deploy**. Two minutes. Copy the URL Vercel gives you, like
   `https://ai-voice-platform-v2.vercel.app`.

---

## 4. Tell the backend about the frontend

Back in Railway, backend service, **Variables**, edit `CORS_ORIGINS`:

```
CORS_ORIGINS=http://localhost:5173,https://ai-voice-platform-v2.vercel.app
```

No spaces after the comma. No trailing slash on the URL. Railway redeploys
on save.

Without this the browser blocks every request with a CORS error and the
footer says the backend is unreachable, even though it is fine.

---

## 5. Test

Open the Vercel URL on your phone, not your laptop. That is the real test:
different network, different device, nothing local involved.

- Footer says **backend ok, db connected**
- Submit the form, allow the microphone
- Maya greets you by name
- `conversations` in Supabase shows both roles and a summary

---

## When something breaks

| Symptom | Look at |
|---|---|
| Footer says backend unreachable | Railway backend logs, and `CORS_ORIGINS` |
| Health says database degraded | `SUPABASE_URL` and `SUPABASE_SECRET_KEY` on Railway |
| Call connects, nobody speaks | Railway agent logs, same messages you saw locally |
| `registered worker` never appears | LiveKit values on the agent service |
| Agent says 401 fetching context | `AGENT_API_KEY` differs between the two services |

The agent writes the same log lines on Railway as it did in `agent.log` on
your laptop. Every fault we found locally would print the same way there.

---

## Later: Plivo

The phone path needs three more things on the backend service, and nothing
on the others:

```
TELEPHONY_ENABLED=true
CALL_TRANSPORT=phone
PLIVO_AUTH_ID=
PLIVO_AUTH_TOKEN=
PLIVO_FROM_NUMBER=
```

`PUBLIC_BASE_URL` is already set to the Railway domain, which is what Plivo
needs to fetch call instructions. No ngrok in production. Follow
`docs/PLIVO-SETUP.md` from Stage 1.

---

## Cost

| Service | Plan | Roughly |
|---|---|---|
| Railway | Hobby, two services | $5/month base plus usage, typically $10 to $15 |
| Vercel | Hobby | free |
| Supabase | Free | free until 500 MB |
| LiveKit | Build | free to 1,000 agent minutes, then a hard stop |
| Groq | free tier | free at test volumes |
| Sarvam | pay as you go | about 6 to 7 rupees per three-minute call |

The first real cost decision is LiveKit's Scale plan for region pinning,
which is only needed for the phone path. Nothing in this guide touches it.
