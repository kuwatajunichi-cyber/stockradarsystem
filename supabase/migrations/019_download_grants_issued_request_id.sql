-- Idempotent follow-up for environments that applied 017/018 before the unique
-- issued request_id index and timestamptz-safe 30d window.
-- Safe if 017/018 already include these objects (production 2026-09-08).

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS download_grants_issued_request_id
  ON public.download_grants (request_id)
  WHERE mint_result = 'issued';

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
WHERE started_at_utc >= now() - interval '30 days'
GROUP BY workflow;

REVOKE ALL ON TABLE public.ops_runs_success_rate_30d FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.ops_runs_success_rate_30d TO service_role;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'download_grants_issued_request_id'
  ) THEN
    RAISE EXCEPTION '019 check failed: missing unique issued request_id index';
  END IF;
END $$;

COMMIT;
