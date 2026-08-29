-- ADR-005 P3: commit monthly snapshot with backfill request/outbox.
-- Apply after 011_adr005_monthly_new_core.sql.
-- Audit fix: release_month advisory lock + canonical winner/loser (ADR-005 section 1.1-1.2).

BEGIN;

CREATE OR REPLACE FUNCTION public.list_committed_monthly_snapshot_rows()
RETURNS TABLE (
  id UUID,
  monthly_tag TEXT,
  snapshot_date DATE,
  github_run_id BIGINT,
  object_keys JSONB,
  status TEXT
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id, monthly_tag, snapshot_date, github_run_id, object_keys, status
  FROM public.monthly_snapshots
  WHERE status = 'committed'
  ORDER BY snapshot_date DESC, github_run_id DESC;
$$;

CREATE OR REPLACE FUNCTION public.get_adr005_feature_start_release_month()
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT feature_start_release_month
  FROM public.adr005_runtime_config
  WHERE config_key = 'monthly_new_core'
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.commit_monthly_snapshot_with_backfill_request(
  p_snapshot_id UUID,
  p_release_month TEXT,
  p_request_id TEXT,
  p_metric_set_version_id UUID,
  p_previous_monthly_tag TEXT,
  p_current_core_logical_digest TEXT,
  p_added_codes JSONB,
  p_added_codes_digest TEXT,
  p_partition_codes_digest TEXT,
  p_expected_trade_dates JSONB,
  p_expected_trade_dates_digest TEXT,
  p_calendar_version TEXT,
  p_outcome TEXT DEFAULT 'runnable',
  p_reason_code TEXT DEFAULT NULL,
  p_partition_index INT DEFAULT 0,
  p_partition_count INT DEFAULT 1
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_snap public.monthly_snapshots%ROWTYPE;
  v_status TEXT;
  v_is_winner BOOLEAN;
  v_winner_id UUID;
  v_winner_request_id TEXT;
  v_old RECORD;
BEGIN
  IF p_partition_index <> 0 OR p_partition_count <> 1 THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: only identity (0,1) in P3';
  END IF;
  IF p_outcome NOT IN ('runnable', 'noop', 'blocked', 'grandfather') THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: invalid outcome %', p_outcome;
  END IF;
  IF p_release_month IS NULL OR p_release_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: invalid release_month';
  END IF;

  -- ADR-005 section 1.1: single-bigint lock on release_month (not snapshot id alone).
  PERFORM pg_advisory_xact_lock(hashtextextended('mnc:' || p_release_month, 0));

  SELECT * INTO v_snap FROM public.monthly_snapshots WHERE id = p_snapshot_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: snapshot % not found', p_snapshot_id;
  END IF;
  IF to_char(v_snap.snapshot_date, 'YYYY-MM') <> p_release_month THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: snapshot_date month mismatch';
  END IF;
  IF v_snap.status = 'committed' THEN
    RETURN jsonb_build_object(
      'snapshot_id', v_snap.id,
      'monthly_tag', v_snap.monthly_tag,
      'noop', true,
      'request_id', NULL,
      'outcome', p_outcome,
      'link_role', NULL
    );
  END IF;
  IF v_snap.status <> 'pending' THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: snapshot % not pending', p_snapshot_id;
  END IF;

  UPDATE public.monthly_snapshots
  SET status = 'committed', committed_at_utc = COALESCE(committed_at_utc, now())
  WHERE id = p_snapshot_id;

  -- Re-evaluate canonical_release_for_month inside the lock (last-wins).
  SELECT id INTO v_winner_id
  FROM public.monthly_snapshots
  WHERE status = 'committed'
    AND to_char(snapshot_date, 'YYYY-MM') = p_release_month
  ORDER BY snapshot_date DESC, github_run_id DESC
  LIMIT 1;

  v_is_winner := (v_winner_id = p_snapshot_id);

  IF NOT v_is_winner THEN
    -- Loser: no request INSERT. Link to current winner primary request if any.
    SELECT rl.request_id INTO v_winner_request_id
    FROM public.request_release_links rl
    WHERE rl.monthly_snapshot_id = v_winner_id
      AND rl.link_role = 'canonical_winner'
    ORDER BY rl.created_at_utc ASC
    LIMIT 1;

    IF v_winner_request_id IS NOT NULL THEN
      INSERT INTO public.request_release_links (
        monthly_snapshot_id, request_id, link_role
      ) VALUES (
        p_snapshot_id, v_winner_request_id, 'noncanonical_loser'
      )
      ON CONFLICT DO NOTHING;
    END IF;

    RETURN jsonb_build_object(
      'snapshot_id', p_snapshot_id,
      'monthly_tag', v_snap.monthly_tag,
      'request_id', NULL,
      'outcome', p_outcome,
      'link_role', 'noncanonical_loser',
      'winner_snapshot_id', v_winner_id,
      'winner_request_id', v_winner_request_id
    );
  END IF;

  -- Demote prior winners in this month: DELETE canonical_winner links, supersede old requests,
  -- invalidate non-terminal outbox, then INSERT loser rows against the new primary request.
  FOR v_old IN
    SELECT rl.monthly_snapshot_id AS old_snap, rl.request_id AS old_req
    FROM public.request_release_links rl
    JOIN public.monthly_snapshots ms ON ms.id = rl.monthly_snapshot_id
    WHERE rl.link_role = 'canonical_winner'
      AND to_char(ms.snapshot_date, 'YYYY-MM') = p_release_month
      AND rl.monthly_snapshot_id <> p_snapshot_id
  LOOP
    DELETE FROM public.request_release_links
    WHERE monthly_snapshot_id = v_old.old_snap
      AND link_role = 'canonical_winner';

    UPDATE public.monthly_new_core_backfill_requests
    SET status = 'superseded',
        successor_request_id = p_request_id
    WHERE id = v_old.old_req
      AND status NOT IN ('completed', 'noop', 'blocked', 'grandfather', 'superseded');

    UPDATE public.monthly_new_core_backfill_outbox
    SET status = 'done',
        done_at_utc = COALESCE(done_at_utc, now()),
        last_error = 'superseded_by_new_canonical_winner'
    WHERE request_id = v_old.old_req
      AND status IN ('pending', 'claimed', 'dispatched', 'failed');
  END LOOP;

  IF p_request_id IS NULL OR p_request_id !~ '^mnc-v1-[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'commit_monthly_snapshot_with_backfill_request: invalid request_id';
  END IF;

  v_status := CASE p_outcome
    WHEN 'runnable' THEN 'dispatch_pending'
    ELSE p_outcome
  END;

  INSERT INTO public.monthly_new_core_backfill_requests (
    id,
    monthly_snapshot_id,
    release_month,
    previous_monthly_tag,
    current_core_logical_digest,
    metric_set_version_id,
    added_codes,
    added_codes_digest,
    partition_index,
    partition_count,
    partition_codes_digest,
    expected_trade_dates,
    expected_trade_dates_digest,
    calendar_version,
    status,
    reason_code
  ) VALUES (
    p_request_id,
    p_snapshot_id,
    p_release_month,
    p_previous_monthly_tag,
    p_current_core_logical_digest,
    p_metric_set_version_id,
    COALESCE(p_added_codes, '[]'::jsonb),
    p_added_codes_digest,
    p_partition_index,
    p_partition_count,
    p_partition_codes_digest,
    COALESCE(p_expected_trade_dates, '[]'::jsonb),
    p_expected_trade_dates_digest,
    COALESCE(p_calendar_version, 'jpx_calendar_v1'),
    v_status,
    p_reason_code
  )
  ON CONFLICT (id) DO NOTHING;

  -- After winner request exists, attach loser links for demoted snapshots.
  FOR v_old IN
    SELECT ms.id AS old_snap
    FROM public.monthly_snapshots ms
    WHERE ms.status = 'committed'
      AND to_char(ms.snapshot_date, 'YYYY-MM') = p_release_month
      AND ms.id <> p_snapshot_id
  LOOP
    INSERT INTO public.request_release_links (
      monthly_snapshot_id, request_id, link_role
    ) VALUES (
      v_old.old_snap, p_request_id, 'noncanonical_loser'
    )
    ON CONFLICT DO NOTHING;
  END LOOP;

  INSERT INTO public.request_release_links (
    monthly_snapshot_id, request_id, link_role
  ) VALUES (
    p_snapshot_id, p_request_id, 'canonical_winner'
  )
  ON CONFLICT DO NOTHING;

  IF p_outcome = 'runnable' THEN
    INSERT INTO public.monthly_new_core_backfill_outbox (
      request_id, chunk_seq, status
    ) VALUES (
      p_request_id, 0, 'pending'
    )
    ON CONFLICT (request_id, chunk_seq) DO NOTHING;
  END IF;

  RETURN jsonb_build_object(
    'snapshot_id', p_snapshot_id,
    'monthly_tag', v_snap.monthly_tag,
    'request_id', p_request_id,
    'outcome', p_outcome,
    'reason_code', p_reason_code,
    'link_role', 'canonical_winner'
  );
END;
$$;

REVOKE ALL ON FUNCTION public.list_committed_monthly_snapshot_rows()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_committed_monthly_snapshot_rows() TO service_role;

REVOKE ALL ON FUNCTION public.get_adr005_feature_start_release_month()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_adr005_feature_start_release_month() TO service_role;

REVOKE ALL ON FUNCTION public.commit_monthly_snapshot_with_backfill_request(
  uuid, text, text, uuid, text, text, jsonb, text, text, jsonb, text, text, text, text, int, int
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_monthly_snapshot_with_backfill_request(
  uuid, text, text, uuid, text, text, jsonb, text, text, jsonb, text, text, text, text, int, int
) TO service_role;

COMMIT;
