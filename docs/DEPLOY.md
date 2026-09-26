# Deploying

Two ways to run this outside the laptop. Start with the free one; move to
the paid one when real leads start.

| | Free (testing and demos) | Paid (real leads, from 1,000 calls a day) |
|---|---|---|
| Frontend | Vercel Hobby | Vercel Hobby or Pro |
| Backend | Render free web service, Singapore | Fly.io, Mumbai |
| Agent | LiveKit Cloud hosted agent, Build plan | Fly.io, Mumbai (or LiveKit Cloud paid) |
| Database | Supabase Free | Supabase Pro |
| Cost | 0 | about $10 to $15 a month for the two machines, plus usage |

Free tier limits that matter: LiveKit Build gives 1,000 agent minutes and
1,000 SIP minutes a month (roughly 300 test calls) and up to 5 calls at
once; the hosted agent may take 10 to 20 seconds to wake after sitting
idle, so the first call after a quiet hour can start with a short silence.
Render's free backend sleeps after fifteen idle minutes; section 3 has the
keep-awake ping. Neither limit exists on the paid path.

Do the steps in order. Each one produces a value the next one needs.

---

## 0. Push to GitHub

Vercel and Render deploy from GitHub. LiveKit deploys from your laptop.

```powershell
cd "D:\Lemniscate Growth\ai-voice-platform-v2"
git init
git add .
git status
```

Look at the list. It must contain no `.env` file from any folder, no
`agent.log`, no `agent-log.txt`. `.gitignore` excludes them, so it will not,
but look anyway. Then:

```powershell
git commit -m "Voice platform: calls, bookings, meetings, WhatsApp, dashboard"
```

Create an empty **private** repository on github.com (no README, no
.gitignore, leave it empty), then:

```powershell
git remote add origin https://github.com/YOUR-USER/ai-voice-platform-v2.git
git branch -M main
git push -u origin main
```

Final check, must print nothing:

```powershell
git ls-files | Select-String "\.env$"
```

---

## 1. Backend on Render (free)

`render.yaml` at the repository root describes the service, so Render
builds it from that file.

1. render.com, sign in with GitHub.
2. **New** > **Blueprint**. Pick the repository. Render reads `render.yaml`
   and shows one service, `lg-maya-backend`, region Singapore, plan Free.
3. It asks for every value marked `sync: false`. Paste them from your local
   `backend\.env`, with two exceptions:
   - `CORS_ORIGINS`: enter `http://localhost:5173` for now. The Vercel
     address is added in step 4.
   - Anything you do not use (for example the Zoom values if you only use
     Google Meet): leave blank.
4. **Apply**. The first build takes three to five minutes.
5. Your backend address is on the service page, like
   `https://lg-maya-backend.onrender.com`. Open
   `https://lg-maya-backend.onrender.com/api/health`. You want
   `"database": "connected"`.
6. In **Logs** you want the same startup block you see locally: `Call
   transport phone`, `Telephony plivo ...`, `Bookings ...`, `Form brakes 5
   per address per hour, 60 minute gap per number`.

### Keep it awake

The free instance sleeps after fifteen idle minutes and takes about a
minute to wake, which a lead experiences as a broken form. Fix it with a
free pinger:

1. cron-job.org (free, no card). Create an account.
2. **Create cronjob**: URL `https://lg-maya-backend.onrender.com/api/health`,
   schedule every 10 minutes.
3. Save. The backend now stays warm around the clock. Render's free
   allowance (750 instance hours a month) covers one service running all
   month.

---

## 2. Agent on LiveKit Cloud (free)

LiveKit runs the agent for you, next to its own media servers, and injects
the LiveKit URL, key and secret itself. You supply everything else from
`agent\.env`.

1. Install the LiveKit CLI:

   ```powershell
   winget install LiveKit.LiveKitCLI
   ```

   Close and reopen the terminal afterwards.

2. Link the CLI to your LiveKit Cloud project (opens the browser once):

   ```powershell
   lk cloud auth
   lk project list
   ```

   If more than one project shows, `lk project set-default "<name>"` for the
   one the backend uses.

3. Make a secrets file from your `.env`, without the three LiveKit lines
   (LiveKit sets those itself and refuses them in a secrets file), and with
   the backend address from step 1:

   ```powershell
   cd "D:\Lemniscate Growth\ai-voice-platform-v2\agent"
   Get-Content .env | Where-Object { $_ -match '^[A-Z0-9_]+=' -and $_ -notmatch '^LIVEKIT_' } | Set-Content .env.production.local
   notepad .env.production.local
   ```

   Change one line:

   ```
   BACKEND_BASE_URL=https://lg-maya-backend.onrender.com/api
   ```

   Confirm `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` are set. The file name
   ends in `.local`, so git ignores it.

4. Create and deploy the agent:

   ```powershell
   lk agent create --secrets-file .env.production.local
   ```

   This builds the image from `agent/Dockerfile` (five to ten minutes the
   first time; it bakes the turn detector model files in), registers the
   agent, and writes `livekit.toml` next to the Dockerfile. Commit that
   file; it holds the agent id, not secrets.

5. Watch it come up:

   ```powershell
   lk agent status
   lk agent logs
   ```

   In the logs you want `registered worker`. That line means Maya is live.

**Now stop the local agent on your laptop.** Two agents on one LiveKit
project both accept calls and you will not know which one answered. From
now on run only the backend and frontend locally when you develop, or set
a different `AGENT_ROOM_PREFIX` locally.

---

## 3. Frontend on Vercel (free)

1. vercel.com, sign in with GitHub, **Add New** > **Project**, import the
   repository.
2. **Root Directory**: Edit, choose `frontend`.
3. Framework preset auto detects **Vite**. Build command `npm run build`,
   output `dist`. Leave as detected.
4. **Environment Variables**, one entry:

   ```
   VITE_API_BASE_URL=https://lg-maya-backend.onrender.com/api
   ```

5. **Deploy**. Two minutes. Copy the address Vercel gives you, like
   `https://ai-voice-platform-v2.vercel.app`.

---

## 4. Tell the backend about the frontend

Render dashboard > `lg-maya-backend` > **Environment** > edit
`CORS_ORIGINS`:

```
http://localhost:5173,https://ai-voice-platform-v2.vercel.app
```

No spaces after the comma, no trailing slash. Save; Render redeploys.

Without this the browser refuses every request with a CORS error and the
page footer says the backend is unreachable, even though it is fine.

---

## 5. Test from a phone, not the laptop

Open the Vercel address on your phone over mobile data. Different network,
different device, nothing local involved.

- Footer says backend ok, db connected.
- Submit the form. Your phone rings within a few seconds.
- Maya greets you by name, asks the language, books a slot.
- The WhatsApp with the Google Meet or Zoom link arrives.
- Dashboard (`/#/counsellor` on the Vercel address, with `DASHBOARD_KEY`)
  shows the booking.
- Submit the form again with the same number: the page says the number was
  called minutes ago and no second call is placed. That is the cooldown
  working.

Watch both services while you do it: `lk agent logs` in one window, the
Render **Logs** tab in the browser.

---

## Changing something later

| Change | Do |
|---|---|
| Code in `backend/` | `git push`; Render redeploys on its own |
| Code in `frontend/` | `git push`; Vercel redeploys on its own |
| Code in `agent/` | `cd agent; lk agent deploy` |
| Backend env value | Render > Environment > edit > Save |
| Agent env value | edit `.env.production.local`, then `lk agent update-secrets --secrets-file .env.production.local` |
| New WhatsApp token | Render > Environment > `WHATSAPP_ACCESS_TOKEN` |
| Restart or roll back the agent | `lk agent restart`, or `lk agent rollback` to the previous build (`lk agent --help` lists every subcommand) |
| Read logs | `lk agent logs`; Render Logs tab |

---

## When something breaks

| Symptom | Look at |
|---|---|
| Footer says backend unreachable | Render logs, `CORS_ORIGINS`, and whether the instance is asleep (first request after idle takes a minute) |
| Health says database degraded | `SUPABASE_URL` and `SUPABASE_SECRET_KEY` on Render |
| Form accepted, phone never rings | Render logs for the Plivo line; `PLIVO_*` and `LIVEKIT_SIP_TRUNK_ID` |
| Phone rings, silence for ten seconds, then Maya | hosted agent waking from idle; free plan behaviour |
| Phone rings, nobody ever speaks | `lk agent logs`, same messages you saw locally |
| `registered worker` never appears | `lk agent status`; rebuild with `lk agent deploy` |
| Agent says 401 fetching context | `AGENT_API_KEY` differs between Render and the agent secrets |
| Page says "too many submissions" while testing | `LEAD_MAX_PER_IP_PER_HOUR` on Render; raise for the day, or wait an hour |
| Second call to the same number skipped | `LEAD_PHONE_COOLDOWN_MINUTES`; set 0 on Render to disable while testing |
| Calls stop mid month | LiveKit Build plan minutes used up; dashboard > Usage |

---

## Later: the paid path (Fly.io, Mumbai)

When real leads start, move the backend and the agent to Fly.io in Mumbai.
Every hop of the audio path then stays inside India (Plivo, LiveKit's India
region, Sarvam, your machines), the agent never sleeps, and there are no
monthly minute caps beyond what you pay for. `backend/fly.toml` and
`agent/fly.toml` are ready for it.

1. Install Fly: `pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"`,
   then `fly auth signup` (card required).
2. Backend, from `backend`: `fly apps create lg-maya-backend`, copy `.env`
   to `.env.production.local` with `APP_ENV=production`, then
   `Get-Content .env.production.local | Where-Object { $_ -match '^[A-Z0-9_]+=' } | fly secrets import --stage`
   and `fly deploy`. Address: `https://lg-maya-backend.fly.dev`.
3. Agent, from `agent`: `fly apps create lg-maya-agent`, same secrets
   import (this time keep the `LIVEKIT_` lines, Fly does not inject them),
   `BACKEND_BASE_URL` pointing at the Fly backend, `fly deploy`. Then
   remove the hosted one (`lk agent delete`, see `lk agent --help`) so only
   one agent answers.
4. Vercel: change `VITE_API_BASE_URL` to the Fly backend and redeploy.
5. Render: delete the service, and the cron-job.org ping.

The rest of the hardening list applies at the same time: paid Gemini with
OpenAI fallback, paid Sarvam, LiveKit and Plivo plans with concurrency
checked, a permanent WhatsApp token, Supabase Pro, monitoring, and a load
test.
