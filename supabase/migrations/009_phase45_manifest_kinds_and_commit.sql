-- Phase 4.5: manifest object kinds, commit staging clear, object-set digest lock.
-- Apply after 008_phase45_batch_object_rpcs.sql.

BEGIN;

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT con.conname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE nsp.nspname = 'public'
      AND rel.relname = 'derived_object_index'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%object_kind IN%'
  LOOP
    EXECUTE format('ALTER TABLE public.derived_object_index DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

ALTER TABLE derived_object_index
  ADD CONSTRAINT derived_object_index_object_kind_check
  CHECK (object_kind IN ('snapshot', 'series', 'snapshot_manifest', 'series_manifest'));

ALTER TABLE derived_object_index DROP CONSTRAINT IF EXISTS derived_object_shape;

ALTER TABLE derived_object_index
  ADD CONSTRAINT derived_object_shape CHECK (
    (
      object_kind IN ('snapshot', 'snapshot_manifest')
      AND trade_date IS NOT NULL
      AND instrument_code IS NULL
      AND series_year IS NULL
    )
    OR (
      object_kind IN ('series', 'series_manifest')
      AND instrument_code IS NOT NULL
      AND series_year IS NOT NULL
      AND trade_date IS NULL
    )
  );

CREATE OR REPLACE FUNCTION set_pending_generation_object_set_digest(
  p_generation_id UUID,
  p_expected_object_set_digest TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
BEGIN
  IF p_expected_object_set_digest IS NULL OR p_expected_object_set_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'set_pending_generation_object_set_digest: digest must be 64 hex chars';
  END IF;
  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'set_pending_generation_object_set_digest: generation % not found', p_generation_id;
  END IF;
  IF v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'set_pending_generation_object_set_digest: generation % not pending', p_generation_id;
  END IF;
  IF v_gen.expected_object_set_digest IS NOT NULL
     AND v_gen.expected_object_set_digest <> p_expected_object_set_digest THEN
    RAISE EXCEPTION 'set_pending_generation_object_set_digest: digest mismatch';
  END IF;
  UPDATE derived_generation_runs
  SET expected_object_set_digest = p_expected_object_set_digest,
      updated_at_utc = now()
  WHERE id = p_generation_id;
  RETURN p_generation_id;
END;
$$;

CREATE OR REPLACE FUNCTION commit_derived_generation(
  p_generation_id UUID,
  p_new_digest TEXT,
  p_expected_old_digest TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_obj_count INT;
  v_uploaded_count INT;
  v_set_uuid UUID;
  v_current_snapshot_digest TEXT;
BEGIN
  v_set_uuid := NULL;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_generation_id::text, 0));

  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'commit_derived_generation: generation % not found', p_generation_id;
  END IF;
  IF v_gen.status = 'committed' THEN
    RETURN p_generation_id;
  END IF;
  IF v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'commit_derived_generation: generation % not pending', p_generation_id;
  END IF;

  v_set_uuid := v_gen.metric_set_version_id;
  PERFORM pg_advisory_xact_lock(
    hashtextextended(v_set_uuid::text || ':' || v_gen.trade_date::text, 0)
  );

  IF p_expected_old_digest IS NOT NULL THEN
    SELECT d.logical_digest INTO v_current_snapshot_digest
    FROM derived_object_index d
    WHERE d.metric_set_version_id = v_set_uuid
      AND d.trade_date = v_gen.trade_date
      AND d.object_kind = 'snapshot'
      AND d.status = 'committed'
    ORDER BY d.committed_at_utc DESC NULLS LAST
    LIMIT 1;

    IF v_current_snapshot_digest IS NOT NULL
       AND v_current_snapshot_digest <> p_expected_old_digest THEN
      RAISE EXCEPTION 'commit_derived_generation: expected_old_digest mismatch (current=% expected=%)',
        v_current_snapshot_digest, p_expected_old_digest;
    END IF;
    IF v_current_snapshot_digest IS NULL AND p_expected_old_digest IS NOT NULL THEN
      RAISE EXCEPTION 'commit_derived_generation: expected_old_digest provided but no committed snapshot';
    END IF;
  END IF;

  IF v_gen.declared_new_digest IS NOT NULL AND p_new_digest IS DISTINCT FROM v_gen.declared_new_digest THEN
    RAISE EXCEPTION 'commit_derived_generation: new_digest mismatch';
  END IF;

  SELECT count(*) INTO v_obj_count
  FROM derived_object_index
  WHERE generation_id = p_generation_id AND status = 'pending';

  SELECT count(*) INTO v_uploaded_count
  FROM derived_object_index
  WHERE generation_id = p_generation_id
    AND status = 'pending'
    AND upload_verified_at IS NOT NULL
    AND byte_sha256 IS NOT NULL
    AND size_bytes IS NOT NULL;

  IF v_gen.expected_object_count IS NULL THEN
    RAISE EXCEPTION 'commit_derived_generation: expected_object_count is required';
  END IF;
  IF v_obj_count <> v_gen.expected_object_count THEN
    RAISE EXCEPTION 'commit_derived_generation: expected object count mismatch';
  END IF;
  IF v_obj_count = 0 OR v_obj_count <> v_uploaded_count THEN
    RAISE EXCEPTION 'commit_derived_generation: not all objects uploaded';
  END IF;

  IF v_gen.expected_object_set_digest IS NULL THEN
    RAISE EXCEPTION 'commit_derived_generation: expected_object_set_digest is required';
  END IF;
  PERFORM 1 FROM (
    SELECT encode(
      sha256(convert_to(string_agg(object_key, E'\n' ORDER BY object_key), 'UTF8')),
      'hex'
    ) AS digest
    FROM derived_object_index
    WHERE generation_id = p_generation_id AND status = 'pending'
  ) AS computed
  WHERE computed.digest <> v_gen.expected_object_set_digest;
  IF FOUND THEN
    RAISE EXCEPTION 'commit_derived_generation: object_set_digest mismatch';
  END IF;

  IF v_gen.artifact_profile = 'snapshot_series_latest' THEN
    IF NOT EXISTS (
      SELECT 1 FROM latest_derived_observations_staging
      WHERE generation_id = p_generation_id
    ) THEN
      RAISE EXCEPTION 'commit_derived_generation: latest staging required for profile';
    END IF;
    IF v_gen.expected_latest_set_digest IS NOT NULL THEN
      PERFORM 1 FROM (
        SELECT encode(
          sha256(convert_to(string_agg(instrument_code, E'\n' ORDER BY instrument_code), 'UTF8')),
          'hex'
        ) AS digest
        FROM latest_derived_observations_staging
        WHERE generation_id = p_generation_id
      ) AS computed
      WHERE computed.digest <> v_gen.expected_latest_set_digest;
      IF FOUND THEN
        RAISE EXCEPTION 'commit_derived_generation: latest_set_digest mismatch';
      END IF;
    END IF;
  END IF;

  IF v_gen.artifact_profile IN ('snapshot_only', 'snapshot_series', 'snapshot_series_latest') THEN
    UPDATE derived_object_index d
    SET status = 'orphan'
    WHERE d.object_kind IN ('snapshot', 'snapshot_manifest')
      AND d.metric_set_version_id = v_gen.metric_set_version_id
      AND d.trade_date = v_gen.trade_date
      AND d.status = 'committed'
      AND d.generation_id IS DISTINCT FROM p_generation_id;
  END IF;

  IF v_gen.artifact_profile IN ('snapshot_series', 'snapshot_series_latest') THEN
    UPDATE derived_object_index d
    SET status = 'orphan'
    WHERE d.object_kind IN ('series', 'series_manifest')
      AND d.metric_set_version_id = v_gen.metric_set_version_id
      AND d.status = 'committed'
      AND d.generation_id IS DISTINCT FROM p_generation_id
      AND EXISTS (
        SELECT 1 FROM derived_object_index cur
        WHERE cur.generation_id = p_generation_id
          AND cur.object_kind = 'series'
          AND cur.instrument_code = d.instrument_code
          AND cur.series_year = d.series_year
      );
  END IF;

  UPDATE derived_object_index
  SET status = 'committed', committed_at_utc = now()
  WHERE generation_id = p_generation_id AND status = 'pending';

  IF v_gen.artifact_profile = 'snapshot_series_latest' THEN
    INSERT INTO latest_derived_observations (
      instrument_code, metric_set_version_id, trade_date, values_json,
      logical_digest, source_run_id, generation_id, updated_at_utc
    )
    SELECT
      s.instrument_code,
      s.metric_set_version_id,
      s.trade_date,
      s.values_json,
      s.logical_digest,
      s.source_run_id,
      s.generation_id,
      now()
    FROM latest_derived_observations_staging s
    WHERE s.generation_id = p_generation_id
    ON CONFLICT (instrument_code, metric_set_version_id) DO UPDATE SET
      trade_date = EXCLUDED.trade_date,
      values_json = EXCLUDED.values_json,
      logical_digest = EXCLUDED.logical_digest,
      source_run_id = EXCLUDED.source_run_id,
      generation_id = EXCLUDED.generation_id,
      updated_at_utc = now()
    WHERE latest_derived_observations.trade_date <= EXCLUDED.trade_date;
  END IF;

  DELETE FROM latest_derived_observations_staging
  WHERE generation_id = p_generation_id;

  UPDATE derived_generation_runs
  SET status = 'committed',
      new_digest = p_new_digest,
      committed_at_utc = now(),
      updated_at_utc = now()
  WHERE id = p_generation_id;

  RETURN p_generation_id;
END;
$$;

REVOKE ALL ON FUNCTION public.set_pending_generation_object_set_digest(uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_pending_generation_object_set_digest(uuid, text)
  TO service_role;

REVOKE ALL ON FUNCTION public.commit_derived_generation(uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text, text) TO service_role;

COMMIT;
