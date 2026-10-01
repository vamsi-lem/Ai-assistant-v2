-- ---------------------------------------------------------------------------
-- AI Voice Platform v2 - lock the views and functions down
--
-- Run once in the Supabase SQL editor, after 0004. Safe to run twice.
--
-- A Postgres view runs with its owner's rights by default, which lets it
-- bypass row level security on the tables underneath. Supabase flags such
-- views "Unrestricted" because the anon key the browser holds could read
-- them. Two fixes, both here:
--
--   1. security_invoker: the view runs as whoever queries it, so the anon
--      role hits the tables' RLS (on, no policies) and gets nothing. The
--      backend uses the service role, which bypasses RLS, and is unaffected.
--   2. revoke: the browser roles (anon, authenticated) lose access to the
--      views and the two dashboard functions outright.
-- ---------------------------------------------------------------------------

alter view public.lead_overview     set (security_invoker = true);
alter view public.call_overview     set (security_invoker = true);
alter view public.upcoming_bookings set (security_invoker = true);

do $$
begin
  if exists (select 1 from pg_views where schemaname = 'public' and viewname = 'recent_calls') then
    execute 'alter view public.recent_calls set (security_invoker = true)';
    execute 'revoke all on public.recent_calls from anon, authenticated';
  end if;
end $$;

revoke all on public.lead_overview     from anon, authenticated;
revoke all on public.call_overview     from anon, authenticated;
revoke all on public.upcoming_bookings from anon, authenticated;

revoke execute on function public.dashboard_counts(uuid, text) from anon, authenticated, public;
revoke execute on function public.analytics_summary(uuid)      from anon, authenticated, public;
