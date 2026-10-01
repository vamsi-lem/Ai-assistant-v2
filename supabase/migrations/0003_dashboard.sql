-- ---------------------------------------------------------------------------
-- AI Voice Platform v2 - dashboard users, pipeline stage, notes, events
--
-- Run once in the Supabase SQL editor, after 0001 and 0002. Safe to run
-- twice: every statement checks whether its work is already done.
--
-- What this adds:
--   profiles       one row per dashboard user (name, role, active), keyed by
--                  the Supabase Auth user id. Created automatically by a
--                  trigger the moment a user is invited or added.
--   leads          stage (the counsellor's pipeline column, separate from the
--                  call outcome in `status`), assigned_to, score,
--                  preferred_language
--   calls          score, intent, extraction (what Maya learned)
--   lead_notes     notes typed by the team
--   lead_events    the timeline: created, called, booked, assigned, ...
--   bookings       counsellor_id
--
-- Row Level Security stays ON with no policies on every table, so the anon
-- key the browser holds can read nothing. The backend uses the service key.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------

create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text        not null unique,
  name        text        not null default '',
  role        text        not null default 'counsellor',
  active      boolean     not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint profiles_role_check
    check (role in ('admin', 'manager', 'counsellor', 'viewer'))
);

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

alter table public.profiles enable row level security;

-- When Supabase Auth gets a new user (invited from the dashboard, or added in
-- the Supabase console), create the matching profile. Name and role come from
-- the invitation metadata when present.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  wanted_role text := new.raw_user_meta_data ->> 'role';
begin
  insert into public.profiles (id, email, name, role)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(nullif(new.raw_user_meta_data ->> 'name', ''), split_part(coalesce(new.email, ''), '@', 1)),
    case when wanted_role in ('admin', 'manager', 'counsellor', 'viewer') then wanted_role else 'counsellor' end
  )
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Users that existed before this migration (for example the admin you created
-- by hand) get a profile too.
insert into public.profiles (id, email, name, role)
select u.id, coalesce(u.email, ''), split_part(coalesce(u.email, ''), '@', 1), 'counsellor'
from auth.users u
where not exists (select 1 from public.profiles p where p.id = u.id);


-- ---------------------------------------------------------------------------
-- leads: stage, assignment, score, language
-- ---------------------------------------------------------------------------

alter table public.leads add column if not exists stage              text not null default 'new';
alter table public.leads add column if not exists assigned_to        uuid references public.profiles (id) on delete set null;
alter table public.leads add column if not exists score              integer;
alter table public.leads add column if not exists preferred_language text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'leads_stage_check') then
    alter table public.leads add constraint leads_stage_check
      check (stage in ('new', 'contacted', 'qualified', 'appointment', 'converted', 'lost'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'leads_score_check') then
    alter table public.leads add constraint leads_score_check
      check (score is null or (score >= 0 and score <= 100));
  end if;
end $$;

create index if not exists leads_stage_idx       on public.leads (stage);
create index if not exists leads_assigned_to_idx on public.leads (assigned_to);
create index if not exists leads_score_idx       on public.leads (score desc nulls last);
create index if not exists leads_created_at_idx  on public.leads (created_at desc);

-- First fill of the stage from what already happened.
update public.leads l
set stage = 'appointment'
where l.stage = 'new'
  and exists (select 1 from public.bookings b where b.lead_id = l.id and b.status = 'booked');

update public.leads
set stage = 'contacted'
where stage = 'new' and status = 'contacted';

update public.leads
set stage = 'lost'
where stage = 'new' and status = 'do_not_call';


-- ---------------------------------------------------------------------------
-- calls: what Maya learned
-- ---------------------------------------------------------------------------

alter table public.calls add column if not exists score      integer;
alter table public.calls add column if not exists intent     text;
alter table public.calls add column if not exists extraction jsonb not null default '{}'::jsonb;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'calls_score_check') then
    alter table public.calls add constraint calls_score_check
      check (score is null or (score >= 0 and score <= 100));
  end if;
end $$;

create index if not exists calls_lead_id_idx    on public.calls (lead_id);
create index if not exists calls_created_at_idx on public.calls (created_at desc);


-- ---------------------------------------------------------------------------
-- lead_notes
-- ---------------------------------------------------------------------------

create table if not exists public.lead_notes (
  id          uuid primary key default gen_random_uuid(),
  lead_id     uuid        not null references public.leads (id) on delete cascade,
  author_id   uuid        references public.profiles (id) on delete set null,
  body        text        not null,
  created_at  timestamptz not null default now()
);

create index if not exists lead_notes_lead_id_idx on public.lead_notes (lead_id, created_at desc);
alter table public.lead_notes enable row level security;


-- ---------------------------------------------------------------------------
-- lead_events: the timeline on the lead page
--
-- kind is one of: lead_created, call_started, call_ended, booking_created,
-- booking_updated, whatsapp_sent, whatsapp_failed, stage_changed, assigned,
-- note_added, callback_noted. data holds the details as json, for example
-- {"detail": "New to Qualified"}. actor_id is the team member who did it,
-- null when Maya or the system did.
-- ---------------------------------------------------------------------------

create table if not exists public.lead_events (
  id          uuid primary key default gen_random_uuid(),
  lead_id     uuid        not null references public.leads (id) on delete cascade,
  kind        text        not null,
  data        jsonb       not null default '{}'::jsonb,
  actor_id    uuid        references public.profiles (id) on delete set null,
  created_at  timestamptz not null default now()
);

create index if not exists lead_events_lead_id_idx on public.lead_events (lead_id, created_at desc);
alter table public.lead_events enable row level security;

-- Existing leads get their "created" event so the timeline is never empty.
insert into public.lead_events (lead_id, kind, data, created_at)
select l.id, 'lead_created', jsonb_build_object('detail', 'via ' || l.source), l.created_at
from public.leads l
where not exists (select 1 from public.lead_events e where e.lead_id = l.id and e.kind = 'lead_created');


-- ---------------------------------------------------------------------------
-- bookings: who the session is with
-- ---------------------------------------------------------------------------

alter table public.bookings add column if not exists counsellor_id uuid references public.profiles (id) on delete set null;
create index if not exists bookings_counsellor_idx on public.bookings (counsellor_id, scheduled_at);
create index if not exists bookings_scheduled_at_idx on public.bookings (scheduled_at);

-- The dashboard view, now with the counsellor.
drop view if exists public.upcoming_bookings;
create view public.upcoming_bookings as
select
  b.id,
  b.scheduled_at,
  b.timezone,
  b.duration_minutes,
  b.status,
  b.meeting_url,
  b.meeting_provider,
  b.meeting_error,
  b.whatsapp_status,
  b.whatsapp_error,
  b.whatsapp_sent_at,
  b.requested_text,
  b.notes,
  l.id               as lead_id,
  l.name             as lead_name,
  l.phone            as lead_phone,
  l.email            as lead_email,
  l.product_or_course,
  b.call_id,
  b.counsellor_id,
  p.name             as counsellor_name,
  b.created_at
from public.bookings b
join public.leads l on l.id = b.lead_id
left join public.profiles p on p.id = b.counsellor_id
order by b.scheduled_at asc;
