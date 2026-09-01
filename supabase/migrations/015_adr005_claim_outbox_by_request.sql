-- ADR-005: claim_mnc_outbox may target a single request_id (monthly inline drain).
-- Poller keeps calling without p_request_id (global claim). DROP+CREATE so the
-- 3-arg call site remains valid via DEFAULT on the new 4th parameter.

BEGIN;

DROP FUNCTION IF EXISTS public.claim_mnc_outbox(text, int, int);

CREATE OR REPLACE FUNCTION public.claim_mnc_outbox(
  p_claimed_by TEXT,
  p_limit INT DEFAULT 2,
  p_visibility_seconds INT DEFAULT 1200,
  p_request_id TEXT DEFAULT NULL
) RETURNS SETOF public.monthly_new_core_backfill_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF p_claimed_by IS NULL OR trim(p_claimed_by) = ''
     OR p_limit < 1 OR p_limit > 2
     OR p_visibility_seconds < 60 OR p_visibility_seconds > 7200 THEN
    RAISE EXCEPTION 'claim_mnc_outbox: invalid claim parameters';
  END IF;

  PERFORM public.reconcile_mnc_outbox();

  RETURN QUERY
  WITH candidates AS (
    SELECT o.id
    FROM public.monthly_new_core_backfill_outbox o
    JOIN public.monthly_new_core_backfill_requests r ON r.id = o.request_id
    WHERE (
      o.status = 'pending'
      OR (
        o.status = 'failed'
        AND o.attempt_count < o.attempt_budget
        AND o.next_retry_at <= now()
      )
    )
      AND r.status NOT IN (
        'completed', 'noop', 'blocked', 'grandfather', 'paused', 'superseded'
      )
      AND (
        p_request_id IS NULL
        OR trim(p_request_id) = ''
        OR o.request_id::text = trim(p_request_id)
      )
    ORDER BY o.created_at_utc, o.id
    FOR UPDATE OF o SKIP LOCKED
    LIMIT p_limit
  )
  UPDATE public.monthly_new_core_backfill_outbox o
  SET status = 'claimed',
      claimed_by = p_claimed_by,
      attempt_count = o.attempt_count + 1,
      fencing_token = o.fencing_token + 1,
      heartbeat_at = now(),
      visibility_timeout_at = now() + make_interval(secs => p_visibility_seconds),
      next_retry_at = NULL,
      updated_at_utc = now()
  FROM candidates c
  WHERE o.id = c.id
  RETURNING o.*;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_mnc_outbox(text, int, int, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_mnc_outbox(text, int, int, text)
  TO service_role;

COMMIT;
