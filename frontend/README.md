# Frontend

Next.js 14 (App Router), TypeScript, Tailwind. Two faces in one build:

- `/form` the public enquiry form. No login. A lead submits, Maya calls.
- everything else is the counsellor dashboard, behind login.

## Run locally

```powershell
cd frontend
npm install
copy .env.example .env.local     # then fill in the three values
npm run dev                      # http://localhost:3000
```

The backend must be running on port 8000 and its `CORS_ORIGINS` must
include `http://localhost:3000`.

## The three settings

| Variable | What |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | the backend, `http://localhost:8000/api` locally, the Render address on Vercel |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL, used only for sign in |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key, the public browser key, used only for sign in |

Everything with the `NEXT_PUBLIC_` prefix is shipped to the browser. That is
fine for these three and would not be fine for anything else, so nothing else
goes in this file. The Supabase secret key, carrier, LiveKit, Meta and meeting
keys all live in `backend/.env`.

## How data flows

```
screen  ->  src/lib/api/<area>.ts  ->  src/lib/api/client.ts  ->  backend
```

`client.ts` attaches the signed in user's token to every request and turns
backend errors into readable messages. The `lib/api/*` files are the only
place a backend path appears. The browser never queries Supabase tables; it
uses Supabase for sign in only (`lib/api/session.ts`).

## Screens

| Route | Who | What |
|---|---|---|
| `/form` | public | enquiry form, then the call status while the phone rings |
| `/login`, `/set-password` | public | sign in, reset, accept an invitation |
| `/dashboard` | all roles | counts, priority queue by score, today's appointments |
| `/leads` | all roles | Kanban by stage, drag to move, add a lead by hand |
| `/leads/[id]` | all roles | profile, consent, every call with transcript and summary, bookings, notes, timeline, call again |
| `/leads/incoming` | admin, manager | unassigned leads, bulk assign |
| `/calls` | all roles | every call, transcript, what Maya learned, score |
| `/appointments` | admin, manager, counsellor | book a slot with real availability; upcoming list |
| `/analytics` | all roles | stage funnel, sources, call outcomes |
| `/settings` | admin, manager | team and roles (admins edit), Maya's configuration read only |

Roles: admin, manager, counsellor (sees only assigned leads), viewer (read
only). The backend enforces these on every request; the UI only hides what a
role cannot use.

## Layout

```
src/
  app/
    form/            public enquiry form
    login/           sign in and password reset
    set-password/    invitation and reset links land here
    (app)/           dashboard, leads, calls, appointments, analytics, settings
  components/
    layout/          sidebar, topbar, search, brand
    leads/           lead form, board, queue, add lead modal, score chip
    settings/        team panel, voice panel
    providers/       auth guard, role, leads, toasts
    ui/              card, modal, loading and error states
    visuals/         the ring and the orb
  lib/
    api/             one file per backend area, plus client.ts and session.ts
    types.ts         shapes shared with backend/app/schemas.py
    labels.ts        human labels for stored enum values
    format.ts        dates, durations, initials, all in India time
    rbac.ts          roles and permissions
```
