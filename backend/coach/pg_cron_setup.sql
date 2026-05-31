-- Supabase heartbeat: replace the always-on scheduler.run_forever() loop with a
-- pg_cron job that POSTs to the brain's /scheduler/tick on a schedule. This is
-- what lets the backend scale to zero — Supabase (always on) is the clock, and
-- the tick also keeps the free project from pausing after inactivity.
--
-- Apply AFTER the backend is deployed and you know its public URL. Run this in
-- the Supabase SQL editor (it runs as a privileged role; pg_cron must live in
-- the `postgres` database, which the SQL editor uses).
--
-- Replace the two placeholders:
--   <BACKEND_URL>        e.g. https://the-coach-brain.fly.dev   (no trailing slash)
--   <COACH_API_TOKEN>    the same token in .env / your platform secret
--
-- NOTE: the schedule is in UTC (Supabase server time). `*/15 6-22 * * *` is a
-- generous waking-hours window in UTC — shift the hours to cover your local
-- daytime. The nudge engine's own restraint/timing logic decides whether a tick
-- actually fires anything, so a coarse cadence is fine; tighten later if you
-- move to precise per-workout (night-before / pre / post) scheduling.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Idempotent: drop a prior version of the job before (re)creating it.
select cron.unschedule('coach-scheduler-tick')
where exists (select 1 from cron.job where jobname = 'coach-scheduler-tick');

select cron.schedule(
  'coach-scheduler-tick',
  '*/15 6-22 * * *',
  $$
  select net.http_post(
    url     := '<BACKEND_URL>/scheduler/tick',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer <COACH_API_TOKEN>'
    ),
    timeout_milliseconds := 8000
  );
  $$
);

-- Inspect:   select * from cron.job;
-- Recent runs: select * from cron.job_run_details order by start_time desc limit 20;
-- Tear down: select cron.unschedule('coach-scheduler-tick');
