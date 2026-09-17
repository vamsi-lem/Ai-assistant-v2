-- ---------------------------------------------------------------------------
-- AI Voice Platform v2 - initial schema
--
-- Three tables, matching the three collections from v1:
--   leads          one row per form submission
--   calls          one row per call attempt, linked to a lead
--   conversations  one row per call, holding the full transcript
--
-- Row Level Security is ON with no public policies. That means the anon key
-- (the one the browser holds) can read and write NOTHING here. Every write
-- goes through the backend using the service role key, which bypasses RLS.
-- This is deliberate: the browser must never be able to touch lead data.
-- ---------------------------------------------------------------------------

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- leads
-- ---------------------------------------------------------------------------

create table if not exists public.leads (
  id                uuid primary key default gen_random_uuid(),

  name              text        not null,
  phone             text        not null,
  email             text,
  product_or_course text        not null,
  notes             text,

  -- Phase 1 only ever writes 'form'. The column exists so later phases can add
  -- 'whatsapp', 'meta_lead_ads' and so on without a migration.
  source            text        not null default 'form',

  status            text        not null default 'new',

  -- Consent evidence. India prohibits cold calling: you need explicit digital
  -- consent before a commercial call, and you need to be able to prove it.
  -- These four columns ARE that proof. Do not make them nullable-by-habit.
  consent_given     boolean     not null default false,
  consent_at        timestamptz,
  consent_ip        text,
  consent_text      text,

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  constraint leads_source_check
    check (source in ('form', 'whatsapp', 'meta_lead_ads', 'google_forms', 'manual')),
  constraint leads_status_check
    check (status in ('new', 'calling', 'contacted', 'no_answer', 'failed', 'do_not_call'))
);

create index if not exists leads_created_at_idx on public.leads (created_at desc);
create index if not exists leads_phone_idx      on public.leads (phone);
create index if not exists leads_status_idx     on public.leads (status);

drop trigger if exists leads_touch_updated_at on public.leads;
create trigger leads_touch_updated_at
  before update on public.leads
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- calls
-- ---------------------------------------------------------------------------

create table if not exists public.calls (
  id               uuid primary key default gen_random_uuid(),
  lead_id          uuid        not null references public.leads (id) on delete cascade,

  status           text        not null default 'queued',

  -- 'browser' routes the lead into the LiveKit room over WebRTC (no carrier,
  -- no cost, works today). 'phone' dials their mobile through the carrier.
  transport        text        not null default 'browser',

  -- Deterministic: always 'call-<id>'. The agent recovers the call id from it.
  room_name        text,

  -- Which carrier placed the call, and that carrier's own id for it. Null on
  -- the browser path.
  provider         text,
  provider_call_id text,

  error            text,

  started_at       timestamptz,
  ended_at         timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint calls_status_check
    check (status in ('queued', 'ringing', 'in-progress', 'completed', 'failed', 'no-answer', 'busy')),
  constraint calls_transport_check
    check (transport in ('browser', 'phone'))
);

create index if not exists calls_lead_id_idx          on public.calls (lead_id);
create index if not exists calls_room_name_idx        on public.calls (room_name);
create index if not exists calls_provider_call_id_idx on public.calls (provider_call_id);
create index if not exists calls_created_at_idx       on public.calls (created_at desc);

drop trigger if exists calls_touch_updated_at on public.calls;
create trigger calls_touch_updated_at
  before update on public.calls
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- conversations
--
-- One row per call. `messages` holds the whole turn list as jsonb, and the
-- agent REPLACES it on every flush rather than appending. That makes the write
-- idempotent: a retried or duplicated flush can never double up turns.
--
-- Shape of each element:
--   { "role": "user" | "assistant",
--     "text": "...",
--     "at": "2026-09-17T09:14:02.123Z",
--     "interrupted": false }
-- ---------------------------------------------------------------------------

create table if not exists public.conversations (
  id         uuid primary key default gen_random_uuid(),
  call_id    uuid        not null unique references public.calls (id) on delete cascade,

  messages   jsonb       not null default '[]'::jsonb,
  summary    text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists conversations_call_id_idx on public.conversations (call_id);

drop trigger if exists conversations_touch_updated_at on public.conversations;
create trigger conversations_touch_updated_at
  before update on public.conversations
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- Enabled with NO policies. Effect: anon and authenticated roles are denied
-- everything. Only the service role (used by the backend and the agent) can
-- read or write. If you later add a client-facing dashboard, add explicit
-- policies then - do not disable RLS.
-- ---------------------------------------------------------------------------

alter table public.leads         enable row level security;
alter table public.calls         enable row level security;
alter table public.conversations enable row level security;

-- ---------------------------------------------------------------------------
-- Convenience view for eyeballing recent activity in the Supabase table editor.
-- Not used by the application.
-- ---------------------------------------------------------------------------

create or replace view public.recent_calls as
select
  c.id            as call_id,
  c.status,
  c.transport,
  c.room_name,
  l.name          as lead_name,
  l.phone         as lead_phone,
  l.product_or_course,
  jsonb_array_length(coalesce(conv.messages, '[]'::jsonb)) as turns,
  conv.summary,
  c.created_at
from public.calls c
join public.leads l on l.id = c.lead_id
left join public.conversations conv on conv.call_id = c.id
order by c.created_at desc;
