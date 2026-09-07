-- Track A 5.5b ops SQL views over public.runs.
-- Operator SELECT only. Not a user dashboard. P0 inherit: no anon/authenticated grants, no user policies.

BEGIN;

CREATE OR REPLACE VIEW public.ops_runs_by_day
WITH (security_invoker = true) AS
SELECT
  workflow,
  run_date,
  status,
  count(*)::bigint AS run_count,
  min(started_at_utc) AS first_started_at_utc,
  max(finished_at_utc) AS last_finished_at_utc
FROM public.runs
GROUP BY workflow, run_date, status;

CREATE OR REPLACE VIEW public.ops_runs_success_rate_30d
WITH (security_invoker = true) AS
SELECT
  workflow,
  count(*) FILTER (WHERE status = 'success')::bigint AS n_success,
  count(*) FILTER (WHERE status = 'failed')::bigint AS n_failed,
  count(*) FILTER (WHERE status = 'cancelled')::bigint AS n_cancelled,
  count(*) FILTER (
    WHERE status IN ('success', 'failed', 'cancelled')
  )::bigint AS n_terminal,
  count(*) FILTER (WHERE status IN ('pending', 'running'))::bigint AS n_open,
  CASE
    WHEN count(*) FILTER (WHERE status IN ('success', 'failed', 'cancelled')) = 0 THEN NULL
    ELSE round(
      (
        count(*) FILTER (WHERE status = 'success')::numeric
        / count(*) FILTER (WHERE status IN ('success', 'failed', 'cancelled'))::numeric
      ),
      4
    )
  END AS success_rate
FROM public.runs
WHERE started_at_utc >= (now() AT TIME ZONE 'utc') - interval '30 days'
GROUP BY workflow;

REVOKE ALL ON TABLE public.ops_runs_by_day FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.ops_runs_success_rate_30d FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.ops_runs_by_day TO service_role;
GRANT SELECT ON TABLE public.ops_runs_success_rate_30d TO service_role;

DO $$
DECLARE
  views text[] := ARRAY['ops_runs_by_day', 'ops_runs_success_rate_30d'];
  v text;
  r record;
BEGIN
  FOREACH v IN ARRAY views LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = v AND c.relkind = 'v'
    ) THEN
      RAISE EXCEPTION '5.5b check failed: missing view public.%', v;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = ANY (views)
  ) THEN
    RAISE EXCEPTION 'P0 check failed: unexpected RLS policies on ops runs views';
  END IF;

  FOR r IN
    SELECT grantee, table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND table_name = ANY (views)
      AND grantee IN ('anon', 'authenticated', 'PUBLIC')
  LOOP
    RAISE EXCEPTION 'P0 check failed: residual grant % on %.% (%)',
      r.grantee, 'public', r.table_name, r.privilege_type;
  END LOOP;

  FOREACH v IN ARRAY views LOOP
    IF NOT has_table_privilege('service_role', format('public.%I', v), 'SELECT') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing SELECT on %', v;
    END IF;
  END LOOP;
END $$;

COMMIT;
