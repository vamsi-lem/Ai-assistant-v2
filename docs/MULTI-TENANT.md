# Multi-tenant architecture

Not implemented. This is the plan, written while the single-tenant version
was being built, so the decisions made now do not have to be undone later.

## What a tenant is

One client of Lemniscate Growth: a college, a coaching institute, a clinic.
Each tenant gets its own assistant persona, its own courses, its own phone
number, its own leads and transcripts, and its own dashboard. They never
see each other's data. Lemniscate sees all of them.

## The one idea that makes it cheap

Today the agent knows nothing until it calls
`GET /api/calls/{id}/context`. It gets the lead's name, the course, the
notes, and builds Maya's instructions from that. Nothing in the agent says
"Lemniscate" or "Nursing"; those come from `.env` and the lead record.

Multi-tenancy means: **that endpoint also returns the tenant**. Assistant
name, company name, voice, languages, greeting language, allowed topics,
callback rules. The agent stays one process, one codebase, one deployment,
and simply behaves as whichever tenant the call belongs to. No per-client
agent, no per-client prompt file, no per-client deploy.

```
lead form (tenant key)  ->  backend resolves tenant  ->  call-<id> room
                                                              |
                             agent fetches context = lead + tenant settings
                             builds prompt, picks voice, offers languages
```

## Data model

Shared Supabase database, one `tenant_id` column on every table, row level
security so a tenant's API key can only ever read its own rows. This is
the standard SaaS pattern (in Mongo terms: one collection, every document
carries `tenantId`, every query filters on it, enforced in the DB rather
than trusted to the app).

```
tenants
  id, slug, name, status, created_at
  agent_name            "Maya"
  company_name          "ABC College"
  greeting_language     "en-IN"
  offered_languages     ["english","hindi","telugu"]
  tts_speaker           "priya"
  tts_temperature       0.75
  llm_provider          "gemini" | "openai" | "groq" | "sarvam"   (keys stay server-side)
  from_number           "+9180xxxxxxxx"          (their Plivo number)
  consent_window_days   7
  max_concurrent_calls  5
  callback_hours        "10:00-19:00 Asia/Kolkata"

tenant_keys
  id, tenant_id, kind ("public" | "admin"), key_hash, created_at, revoked_at
    public: goes in the website form embed, can only create a lead
    admin:  dashboard and API access to that tenant's data

tenant_courses
  id, tenant_id, name, one_line_description, active
    what Maya may talk about; anything else goes to a counsellor

leads, calls, conversations
  + tenant_id on each (indexed), RLS policy: tenant_id = current tenant
```

Why shared DB with RLS and not a database per tenant: one migration, one
backup, one connection pool, and Supabase enforces isolation at the row
level. A database per tenant is for regulated enterprise deals; if a
client demands it, it is a deployment choice, not a code change.

## Request flow, tenant by tenant

**Lead form.** The embed carries the tenant's public key. `POST /api/leads`
reads it, resolves the tenant, writes `tenant_id` on the lead and the
call. The form UI is the same code with the tenant's name and logo pulled
from `GET /api/tenants/me` using that key.

**Placing the call.** `PLIVO_FROM_NUMBER` moves from `.env` to
`tenants.from_number`. One LiveKit outbound trunk lists every tenant's
number, and the backend passes the tenant's number as `sip_number` on the
dial. The lead sees their college's number, not Lemniscate's.

**The agent.** `fetch_call_context` returns `{lead, tenant, courses}`. The
agent already switches voice language live; it will pick speaker,
temperature, greeting language and offered languages from `tenant` in the
same place. `build_instructions(context)` takes the persona from
`tenant`, the topic boundary from `courses`. Zero branches on tenant
anywhere in the agent.

**Transcripts and callbacks.** Already keyed by call id; they inherit
`tenant_id` from the call. `save_callback` appends to the lead as today.

**Dashboard.** `GET /api/tenants/{id}/calls`, `/leads`, `/conversations`
behind the admin key; the same queries as today plus the tenant filter,
which RLS enforces even if a query forgets it.

## Limits and billing

`calls` already has `started_at` and `ended_at`. Minutes per tenant per
month is one query. `max_concurrent_calls` is checked before dialling
(count of this tenant's calls in `ringing` or `in-progress`), so one
client's campaign cannot starve another's. Sarvam and LiveKit usage is
attributed to tenants from the same call records; no separate metering.

## Secrets

Never per tenant in `.env`. Sarvam, LiveKit and LLM keys are Lemniscate's
and stay platform-wide. A tenant that insists on its own OpenAI key gets a
`tenant_secrets` table encrypted with a platform key, read only by the
backend, never returned by any endpoint.

## Compliance per tenant

Consent and the seven-day window already live on the lead. Per tenant add:
their number series (140 vs service) which decides what Maya may say, their
callback hours, and their own do-not-call list. The compliance gate in
`services/telephony/service.py` already takes the lead; it will take the
tenant too.

## What to keep doing now so this stays cheap

1. Never hard-code a client name, course or number in code. Everything
   like that reads from config or the call context. (True today.)
2. Every new table gets a `tenant_id` column from day one, even if it only
   ever holds one value. Adding the column later means backfilling.
3. Every new endpoint that reads data goes through the same helper that
   will one day add the tenant filter, rather than calling Supabase
   directly from the router.
4. Keep the agent stateless. Anything it needs comes from the context
   endpoint, never from its own `.env` beyond platform keys.

## Migration, when the day comes

1. Add `tenants`, `tenant_keys`, `tenant_courses`. Insert one tenant for
   the current client with today's `.env` values.
2. Add `tenant_id` to `leads`, `calls`, `conversations`, default to that
   tenant, backfill, then make it NOT NULL and add RLS.
3. Move `AGENT_NAME`, `AGENT_COMPANY`, `AGENT_LANGUAGES`,
   `SARVAM_TTS_SPEAKER`, `PLIVO_FROM_NUMBER` out of `.env` into that row.
4. Extend the context endpoint. Extend `build_instructions`. Extend the
   dial to pass `sip_number`.
5. Put the public key in the form embed. Ship the dashboard.

Roughly two weeks of work, none of it a rewrite.
