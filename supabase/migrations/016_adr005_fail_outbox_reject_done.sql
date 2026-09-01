-- ADR-005: fail_mnc_outbox must not rewind a finished (done) chunk.
-- Defends against late heartbeat / worker exception after finish_mnc_outbox_chunk.

BEGIN;

CREATE OR REPLACE FUNCTION public.fail_mnc_outbox(
  p_outbox_id UUID,
  p_fencing_token BIGINT,
  p_error TEXT,
  p_retry_seconds INT DEFAULT 300
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_row public.monthly_new_core_backfill_outbox%ROWTYPE;
BEGIN
  SELECT * INTO v_row
  FROM public.monthly_new_core_backfill_outbox
  WHERE id = p_outbox_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'fail_mnc_outbox: outbox % not found', p_outbox_id;
  END IF;
  IF v_row.fencing_token <> p_fencing_token THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'fencing_mismatch');
  END IF;
  IF v_row.status = 'done' THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'bad_status', 'status', v_row.status);
  END IF;
  UPDATE public.monthly_new_core_backfill_outbox
  SET status = 'failed',
      last_error = left(COALESCE(p_error, 'worker_failed'), 2000),
      next_retry_at = now() + make_interval(secs => GREATEST(60, LEAST(p_retry_seconds, 86400))),
      visibility_timeout_at = NULL,
      updated_at_utc = now()
  WHERE id = p_outbox_id;
  UPDATE public.monthly_new_core_backfill_requests
  SET status = 'failed_retryable',
      reason_code = 'worker_failed',
      updated_at_utc = now()
  WHERE id = v_row.request_id
    AND status NOT IN ('completed', 'noop', 'blocked', 'grandfather', 'superseded');
  RETURN jsonb_build_object('ok', true, 'outbox_id', p_outbox_id, 'status', 'failed');
END;
$$;

REVOKE ALL ON FUNCTION public.fail_mnc_outbox(uuid, bigint, text, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fail_mnc_outbox(uuid, bigint, text, int)
  TO service_role;

COMMIT;
