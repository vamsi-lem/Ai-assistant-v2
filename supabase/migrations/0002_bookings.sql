-- ---------------------------------------------------------------------------
-- AI Voice Platform v2 - bookings
--
-- One row per counsellor slot Maya books on a call: when, for whom, the
-- meeting link that was created, and whether the WhatsApp confirmation
-- reached the lead. The counsellor dashboard reads this table.
--
-- Run once in Supabase -> SQL Editor. Safe to run twice.
-- ---------------------------------------------------------------------------

create table if not exists public.bookings (
  id                  uuid primary key default gen_random_uuid(),
  lead_id             uuid        not null references public.leads (id) on delete cascade,
  call_id             uuid        references public.calls (id) on delete set null,

  -- The slot. Stored in UTC; `timezone` says how the lead said it.
  scheduled_at        timestamptz not null,
  timezone            text        not null default 'Asia/Kolkata',
  duration_minutes    integer     not null default 30,

  -- What the lead actually said ("tomorrow evening six") and what Maya
  -- noted for the counsellor (questions she could not answer).
  requested_text      text,
  notes               text,

  -- The meeting link. Null when no provider is configured or creation failed;
  -- meeting_error says why, so the counsellor can create one by hand.
  meeting_provider    text,
  meeting_url         text,
  meeting_id          text,
  meeting_error       text,

  -- The WhatsApp confirmation to the lead.
  whatsapp_status     text        not null default 'pending',
  whatsapp_message_id text,
  whatsapp_error      text,
  whatsapp_sent_at    timestamptz,

  status              text        not null default 'booked',

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  constraint bookings_whatsapp_status_check
    check (whatsapp_status in ('pending', 'sent', 'failed', 'skipped')),
  constraint bookings_status_check
    check (status in ('booked', 'cancelled', 'completed', 'no_show'))
);

create index if not exists bookings_scheduled_at_idx on public.bookings (scheduled_at);
create index if not exists bookings_lead_id_idx      on public.bookings (lead_id);
create index if not exists bookings_status_idx       on public.bookings (status);

drop trigger if exists bookings_touch_updated_at on public.bookings;
create trigger bookings_touch_updated_at
  before update on public.bookings
  for each row execute function public.touch_updated_at();

-- Same rule as every other table: RLS on, no policies, service role only.
alter table public.bookings enable row level security;

-- What the counsellor dashboard shows, one row per booking with the lead.
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
  b.requested_text,
  b.notes,
  l.id               as lead_id,
  l.name             as lead_name,
  l.phone            as lead_phone,
  l.email            as lead_email,
  l.product_or_course,
  b.call_id,
  b.created_at
from public.bookings b
join public.leads l on l.id = b.lead_id
order by b.scheduled_at asc;
