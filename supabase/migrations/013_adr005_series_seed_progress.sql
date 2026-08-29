-- ADR-005 P5: trade_date progress + series_repair self-approval guard.
-- Apply after 012_adr005_monthly_commit_rpc.sql.

BEGIN;

CREATE OR REPLACE FUNCTION public.commit_trade_date_progress(
  p_request_id TEXT,
  p_trade_date DATE,
  p_write_count INT,
  p_resolved_noop_count INT DEFAULT 0,
  p_generation_id UUID DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_req public.monthly_new_core_backfill_requests%ROWTYPE;
BEGIN
  IF p_write_count < 0 OR p_resolved_noop_count < 0 THEN
    RAISE EXCEPTION 'commit_trade_date_progress: counts must be >= 0';
  END IF;
  SELECT * INTO v_req
  FROM public.monthly_new_core_backfill_requests
  WHERE id = p_request_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'commit_trade_date_progress: request % not found', p_request_id;
  END IF;
  IF v_req.status IN ('completed', 'noop', 'blocked', 'grandfather', 'superseded') THEN
    RETURN jsonb_build_object(
      'request_id', p_request_id,
      'trade_date', p_trade_date,
      'noop', true,
      'status', v_req.status
    );
  END IF;

  UPDATE public.monthly_new_core_backfill_requests
  SET
    last_committed_trade_date = GREATEST(
      COALESCE(last_committed_trade_date, p_trade_date - 1),
      p_trade_date
    ),
    heartbeat_at = now(),
    status = CASE
      WHEN status IN ('dispatch_pending', 'dispatched', 'ohlcv_running', 'ohlcv_ready')
        THEN 'series_running'
      ELSE status
    END
  WHERE id = p_request_id;

  INSERT INTO public.monthly_new_core_backfill_events (
    request_id, event_type, from_status, to_status, reason_code, details, actor
  ) VALUES (
    p_request_id,
    CASE WHEN p_write_count = 0 THEN 'resolved_noop' ELSE 'trade_date_progress' END,
    v_req.status,
    'series_running',
    NULL,
    jsonb_build_object(
      'trade_date', p_trade_date,
      'write_count', p_write_count,
      'resolved_noop_count', p_resolved_noop_count,
      'generation_id', p_generation_id
    ),
    'series_seed_worker'
  );

  RETURN jsonb_build_object(
    'request_id', p_request_id,
    'trade_date', p_trade_date,
    'write_count', p_write_count,
    'resolved_noop_count', p_resolved_noop_count,
    'generation_id', p_generation_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.commit_series_repair(
  p_request_id TEXT,
  p_approver_github_login TEXT,
  p_worker_github_actor TEXT,
  p_reason_code TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF p_approver_github_login IS NULL OR length(trim(p_approver_github_login)) = 0 THEN
    RAISE EXCEPTION 'commit_series_repair: approver required';
  END IF;
  IF lower(trim(p_approver_github_login)) = lower(trim(COALESCE(p_worker_github_actor, ''))) THEN
    RAISE EXCEPTION 'commit_series_repair: self-approval forbidden';
  END IF;
  RETURN jsonb_build_object(
    'request_id', p_request_id,
    'accepted', true,
    'reason_code', p_reason_code,
    'approver_github_login', lower(trim(p_approver_github_login))
  );
END;
$$;

REVOKE ALL ON FUNCTION public.commit_trade_date_progress(text, date, int, int, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_trade_date_progress(text, date, int, int, uuid)
  TO service_role;

REVOKE ALL ON FUNCTION public.commit_series_repair(text, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_series_repair(text, text, text, text)
  TO service_role;

COMMIT;
