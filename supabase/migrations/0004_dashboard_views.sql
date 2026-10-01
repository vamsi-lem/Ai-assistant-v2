-- ---------------------------------------------------------------------------
-- AI Voice Platform v2 - dashboard reads
--
-- Run once in the Supabase SQL editor, after 0003. Safe to run twice.
--
-- The dashboard asks the backend for lists and counts many times a minute.
-- Rather than have the backend stitch leads, calls, bookings and profiles
-- together in Python, the database does it once, here:
--
--   lead_overview        one row per lead with the assignee's name, the last
--                        call time, the call count and the next booking
--   call_overview        one row per call with the lead's name and phone,
--                        the summary, the turn count and the duration
--   dashboard_counts()   the five numbers at the top of the dashboard
--   analytics_summary()  funnel, sources and call outcomes, grouped
--   app_settings         small key/value store; the agent reports its own
--                        configuration here at startup so the dashboard can
--                        show it
--
-- Both functions take the signed in user's id when that user is a
-- counsellor, so the numbers cover only their leads. The backend passes it;
-- the browser never calls these directly.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- lead_overview
-- ---------------------------------------------------------------------------

drop view if exists public.lead_overview;
create view public.lead_overview as
select
  l.id,
  l.name,
  l.phone,
  l.email,
  l.product_or_course,
  l.notes,
  l.source,
  l.status,
  l.stage,
  l.score,
  l.assigned_to,
  p.name                                   as assigned_name,
  l.preferred_language,
  l.consent_given,
  l.consent_at,
  l.created_at,
  l.updated_at,
  lc.last_call_at,
  coalesce(lc.calls_count, 0)              as calls_count,
  nb.next_booking_at
from public.leads l
left join public.profiles p on p.id = l.assigned_to
left join lateral (
  select max(coalesce(c.started_at, c.created_at)) as last_call_at,
         count(*)                                   as calls_count
  from public.calls c
  where c.lead_id = l.id
) lc on true
left join lateral (
  select min(b.scheduled_at) as next_booking_at
  from public.bookings b
  where b.lead_id = l.id and b.status = 'booked' and b.scheduled_at >= now()
) nb on true;


-- ---------------------------------------------------------------------------
-- call_overview
-- ---------------------------------------------------------------------------

drop view if exists public.call_overview;
create view public.call_overview as
select
  c.id,
  c.lead_id,
  l.name                                   as lead_name,
  l.phone                                  as lead_phone,
  l.assigned_to                            as lead_assigned_to,
  c.status,
  c.transport,
  c.started_at,
  c.ended_at,
  case
    when c.started_at is not null and c.ended_at is not null
      then greatest(0, extract(epoch from (c.ended_at - c.started_at)))::integer
    else null
  end                                      as duration_seconds,
  c.error,
  cv.summary,
  c.score,
  c.intent,
  c.extraction,
  coalesce(jsonb_array_length(cv.messages), 0) as turns,
  c.created_at
from public.calls c
join public.leads l on l.id = c.lead_id
left join public.conversations cv on cv.call_id = c.id;


-- ---------------------------------------------------------------------------
-- dashboard_counts(p_assigned)
--
-- Five numbers in one round trip. p_assigned is null for admins, managers
-- and viewers (everything), or a profile id for a counsellor (their leads).
-- "Today" is in the booking timezone passed in, so the count matches the
-- clock on the counsellor's wall, not UTC.
-- ---------------------------------------------------------------------------

create or replace function public.dashboard_counts(p_assigned uuid default null, p_tz text default 'Asia/Kolkata')
returns json
language sql
stable
as $$
  with day as (
    select (date_trunc('day', now() at time zone p_tz)) at time zone p_tz        as start_utc,
           (date_trunc('day', now() at time zone p_tz) + interval '1 day') at time zone p_tz as end_utc
  )
  select json_build_object(
    'leads',              (select count(*) from public.leads l
                             where p_assigned is null or l.assigned_to = p_assigned),
    'qualified',          (select count(*) from public.leads l
                             where l.stage = 'qualified'
                               and (p_assigned is null or l.assigned_to = p_assigned)),
    'converted',          (select count(*) from public.leads l
                             where l.stage = 'converted'
                               and (p_assigned is null or l.assigned_to = p_assigned)),
    'appointments_today', (select count(*) from public.bookings b
                             join public.leads l on l.id = b.lead_id, day
                             where b.status = 'booked'
                               and b.scheduled_at >= day.start_utc and b.scheduled_at < day.end_utc
                               and (p_assigned is null or l.assigned_to = p_assigned or b.counsellor_id = p_assigned)),
    'calls_today',        (select count(*) from public.calls c
                             join public.leads l on l.id = c.lead_id, day
                             where coalesce(c.started_at, c.created_at) >= day.start_utc
                               and coalesce(c.started_at, c.created_at) < day.end_utc
                               and (p_assigned is null or l.assigned_to = p_assigned))
  );
$$;


-- ---------------------------------------------------------------------------
-- analytics_summary(p_assigned)
-- ---------------------------------------------------------------------------

create or replace function public.analytics_summary(p_assigned uuid default null)
returns json
language sql
stable
as $$
  with scoped as (
    select * from public.leads l
    where p_assigned is null or l.assigned_to = p_assigned
  )
  select json_build_object(
    'total',     (select count(*) from scoped),
    'converted', (select count(*) from scoped where stage = 'converted'),
    'funnel',    (select coalesce(json_agg(json_build_object('stage', s.stage, 'n', coalesce(x.n, 0)) order by s.ord), '[]'::json)
                    from (values ('new', 1), ('contacted', 2), ('qualified', 3), ('appointment', 4), ('converted', 5), ('lost', 6)) as s(stage, ord)
                    left join (select stage, count(*) as n from scoped group by stage) x on x.stage = s.stage),
    'sources',   (select coalesce(json_agg(json_build_object('source', source, 'n', n) order by n desc), '[]'::json)
                    from (select source, count(*) as n from scoped group by source) y),
    'calls',     (select coalesce(json_agg(json_build_object('status', status, 'n', n) order by n desc), '[]'::json)
                    from (select c.status, count(*) as n
                          from public.calls c join scoped l on l.id = c.lead_id
                          group by c.status) z)
  );
$$;


-- ---------------------------------------------------------------------------
-- app_settings
-- ---------------------------------------------------------------------------

create table if not exists public.app_settings (
  key         text primary key,
  value       jsonb       not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);

alter table public.app_settings enable row level security;
