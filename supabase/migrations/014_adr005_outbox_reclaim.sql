-- ADR-005: outbox visibility reclaim, heartbeat, finish/fail chunk.
-- Apply after 013_adr005_series_seed_progress.sql.

BEGIN;

CREATE OR REPLACE FUNCTION public.reconcile_mnc_outbox()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_count INT := 0;
BEGIN
  UPDATE public.monthly_new_core_backfill_outbox o
  SET status = 'pending',
      claimed_by = NULL,
      github_run_id = NULL,
      visibility_timeout_at = NULL,
      last_error = COALESCE(o.last_error, 'visibility_timeout_reclaim'),
      updated_at_utc = now()
  WHERE o.status IN ('claimed', 'dispatched')
    AND o.visibility_timeout_at IS NOT NULL
    AND o.visibility_timeout_at <= now();
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_mnc_outbox(
  p_claimed_by TEXT,
  p_limit INT DEFAULT 2,
  p_visibility_seconds INT DEFAULT 1200
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

  -- Reclaim expired claims before selecting (ADR reconciler + defense in depth).
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

CREATE OR REPLACE FUNCTION public.heartbeat_mnc_outbox(
  p_outbox_id UUID,
  p_fencing_token BIGINT,
  p_visibility_seconds INT DEFAULT 1200
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_row public.monthly_new_core_backfill_outbox%ROWTYPE;
BEGIN
  IF p_visibility_seconds < 60 OR p_visibility_seconds > 7200 THEN
    RAISE EXCEPTION 'heartbeat_mnc_outbox: invalid visibility';
  END IF;
  SELECT * INTO v_row
  FROM public.monthly_new_core_backfill_outbox
  WHERE id = p_outbox_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'heartbeat_mnc_outbox: outbox % not found', p_outbox_id;
  END IF;
  IF v_row.fencing_token <> p_fencing_token THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'fencing_mismatch');
  END IF;
  IF v_row.status NOT IN ('claimed', 'dispatched') THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'bad_status', 'status', v_row.status);
  END IF;
  UPDATE public.monthly_new_core_backfill_outbox
  SET heartbeat_at = now(),
      visibility_timeout_at = now() + make_interval(secs => p_visibility_seconds),
      updated_at_utc = now()
  WHERE id = p_outbox_id;
  RETURN jsonb_build_object('ok', true, 'outbox_id', p_outbox_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.mark_mnc_outbox_dispatched(
  p_outbox_id UUID,
  p_fencing_token BIGINT,
  p_github_run_id BIGINT
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
    RAISE EXCEPTION 'mark_mnc_outbox_dispatched: outbox % not found', p_outbox_id;
  END IF;
  IF v_row.fencing_token <> p_fencing_token THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'fencing_mismatch');
  END IF;
  IF v_row.status NOT IN ('claimed', 'dispatched') THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'bad_status', 'status', v_row.status);
  END IF;
  UPDATE public.monthly_new_core_backfill_outbox
  SET status = 'dispatched',
      github_run_id = p_github_run_id,
      updated_at_utc = now()
  WHERE id = p_outbox_id;
  UPDATE public.monthly_new_core_backfill_requests
  SET status = CASE
        WHEN status IN ('dispatch_pending', 'dispatch_failed', 'failed_retryable')
          THEN 'dispatched'
        ELSE status
      END,
      updated_at_utc = now()
  WHERE id = v_row.request_id;
  RETURN jsonb_build_object('ok', true, 'outbox_id', p_outbox_id);
END;
$$;

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

CREATE OR REPLACE FUNCTION public.finish_mnc_outbox_chunk(
  p_outbox_id UUID,
  p_fencing_token BIGINT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_out public.monthly_new_core_backfill_outbox%ROWTYPE;
  v_req public.monthly_new_core_backfill_requests%ROWTYPE;
  v_dates JSONB;
  v_last DATE;
  v_remaining INT := 0;
  v_d TEXT;
  v_next_seq INT;
BEGIN
  SELECT * INTO v_out
  FROM public.monthly_new_core_backfill_outbox
  WHERE id = p_outbox_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'finish_mnc_outbox_chunk: outbox % not found', p_outbox_id;
  END IF;
  IF v_out.fencing_token <> p_fencing_token THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'fencing_mismatch');
  END IF;
  IF v_out.status NOT IN ('claimed', 'dispatched') THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'bad_status', 'status', v_out.status);
  END IF;

  SELECT * INTO v_req
  FROM public.monthly_new_core_backfill_requests
  WHERE id = v_out.request_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'finish_mnc_outbox_chunk: request % not found', v_out.request_id;
  END IF;

  UPDATE public.monthly_new_core_backfill_outbox
  SET status = 'done',
      done_at_utc = now(),
      visibility_timeout_at = NULL,
      updated_at_utc = now()
  WHERE id = p_outbox_id;

  v_dates := COALESCE(v_req.expected_trade_dates, '[]'::jsonb);
  v_last := v_req.last_committed_trade_date;
  FOR v_d IN SELECT jsonb_array_elements_text(v_dates)
  LOOP
    IF v_last IS NULL OR v_d::date > v_last THEN
      v_remaining := v_remaining + 1;
    END IF;
  END LOOP;

  IF v_remaining = 0 THEN
    UPDATE public.monthly_new_core_backfill_requests
    SET status = 'completed',
        completed_at_utc = now(),
        uncommitted_count = 0,
        updated_at_utc = now()
    WHERE id = v_req.id;
    INSERT INTO public.monthly_new_core_backfill_events (
      request_id, event_type, from_status, to_status, reason_code, details, actor
    ) VALUES (
      v_req.id, 'completed', v_req.status, 'completed', NULL,
      jsonb_build_object('outbox_id', p_outbox_id), 'series_seed_worker'
    );
    RETURN jsonb_build_object(
      'ok', true,
      'outbox_id', p_outbox_id,
      'request_status', 'completed',
      'next_outbox', false
    );
  END IF;

  v_next_seq := v_out.chunk_seq + 1;
  INSERT INTO public.monthly_new_core_backfill_outbox (
    request_id, chunk_seq, status, attempt_budget
  ) VALUES (
    v_req.id, v_next_seq, 'pending', v_out.attempt_budget
  )
  ON CONFLICT (request_id, chunk_seq) DO NOTHING;

  UPDATE public.monthly_new_core_backfill_requests
  SET status = 'dispatch_pending',
      uncommitted_count = v_remaining,
      updated_at_utc = now()
  WHERE id = v_req.id;

  INSERT INTO public.monthly_new_core_backfill_events (
    request_id, event_type, from_status, to_status, reason_code, details, actor
  ) VALUES (
    v_req.id, 'chunk_done', v_req.status, 'dispatch_pending', NULL,
    jsonb_build_object(
      'outbox_id', p_outbox_id,
      'next_chunk_seq', v_next_seq,
      'remaining_trade_dates', v_remaining
    ),
    'series_seed_worker'
  );

  RETURN jsonb_build_object(
    'ok', true,
    'outbox_id', p_outbox_id,
    'request_status', 'dispatch_pending',
    'next_outbox', true,
    'next_chunk_seq', v_next_seq,
    'remaining_trade_dates', v_remaining
  );
END;
$$;

REVOKE ALL ON FUNCTION public.reconcile_mnc_outbox()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_mnc_outbox()
  TO service_role;

REVOKE ALL ON FUNCTION public.claim_mnc_outbox(text, int, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_mnc_outbox(text, int, int)
  TO service_role;

REVOKE ALL ON FUNCTION public.heartbeat_mnc_outbox(uuid, bigint, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.heartbeat_mnc_outbox(uuid, bigint, int)
  TO service_role;

REVOKE ALL ON FUNCTION public.mark_mnc_outbox_dispatched(uuid, bigint, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mark_mnc_outbox_dispatched(uuid, bigint, bigint)
  TO service_role;

REVOKE ALL ON FUNCTION public.fail_mnc_outbox(uuid, bigint, text, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fail_mnc_outbox(uuid, bigint, text, int)
  TO service_role;

REVOKE ALL ON FUNCTION public.finish_mnc_outbox_chunk(uuid, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_mnc_outbox_chunk(uuid, bigint)
  TO service_role;

COMMIT;
