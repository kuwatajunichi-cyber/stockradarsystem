-- Phase 4.5 batch object RPCs for derived writer performance (Issue #93).
-- Apply after 007_phase45_commit_expected_old_digest.sql.
-- Client MUST chunk register/mark/stage at 500 rows (PostgREST payload / statement_timeout).

BEGIN;

-- Chunk size contract for callers (Python adapter): 500 objects/rows per RPC invocation.
-- Reuse/conflict for register matches single-object RPC: logical_digest equality.

CREATE OR REPLACE FUNCTION register_pending_derived_objects(
  p_generation_id UUID,
  p_objects JSONB
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '60s'
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_item JSONB;
  v_kind TEXT;
  v_key TEXT;
  v_digest TEXT;
  v_trade_date DATE;
  v_instrument TEXT;
  v_year INT;
  v_layer1 TEXT;
  v_writer TEXT;
  v_existing derived_object_index%ROWTYPE;
  v_id UUID;
  v_seen TEXT[] := ARRAY[]::TEXT[];
  v_coord TEXT;
  v_out JSONB := '[]'::JSONB;
BEGIN
  IF p_objects IS NULL OR jsonb_typeof(p_objects) <> 'array' THEN
    RAISE EXCEPTION 'register_pending_derived_objects: p_objects must be a JSON array';
  END IF;

  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND OR v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'register_pending_derived_objects: generation % not pending', p_generation_id;
  END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_objects)
  LOOP
    v_kind := lower(trim(v_item->>'object_kind'));
    v_key := trim(v_item->>'object_key');
    v_digest := lower(trim(v_item->>'logical_digest'));
    v_trade_date := NULLIF(trim(v_item->>'trade_date'), '')::DATE;
    v_instrument := NULLIF(trim(v_item->>'instrument_code'), '');
    v_year := NULLIF(trim(v_item->>'series_year'), '')::INT;
    v_layer1 := NULLIF(trim(v_item->>'layer1_input_fingerprint'), '');
    v_writer := COALESCE(NULLIF(trim(v_item->>'writer_workflow'), ''), 'derived_writer.yml');

    IF v_kind IS NULL OR v_key IS NULL OR v_key = '' OR v_digest IS NULL OR v_digest !~ '^[a-f0-9]{64}$' THEN
      RAISE EXCEPTION 'register_pending_derived_objects: invalid object payload';
    END IF;

    v_coord := v_kind || '|' || COALESCE(v_trade_date::text, '') || '|' ||
               COALESCE(v_instrument, '') || '|' || COALESCE(v_year::text, '');
    IF v_coord = ANY (v_seen) THEN
      RAISE EXCEPTION 'register_pending_derived_objects: duplicate coordinate in chunk for generation %', p_generation_id;
    END IF;
    v_seen := array_append(v_seen, v_coord);

    SELECT * INTO v_existing
    FROM derived_object_index
    WHERE generation_id = p_generation_id
      AND object_kind = v_kind
      AND trade_date IS NOT DISTINCT FROM v_trade_date
      AND instrument_code IS NOT DISTINCT FROM v_instrument
      AND series_year IS NOT DISTINCT FROM v_year
    FOR UPDATE;

    IF FOUND THEN
      IF v_existing.logical_digest = v_digest THEN
        v_id := v_existing.id;
      ELSE
        RAISE EXCEPTION 'register_pending_derived_objects: coordinate conflict for generation %', p_generation_id;
      END IF;
    ELSE
      INSERT INTO derived_object_index (
        object_kind, metric_set_version_id, trade_date, instrument_code, series_year,
        object_key, logical_digest, layer1_input_fingerprint, writer_workflow,
        generation_id, status
      ) VALUES (
        v_kind, v_gen.metric_set_version_id, v_trade_date, v_instrument, v_year,
        v_key, v_digest, v_layer1, v_writer,
        p_generation_id, 'pending'
      )
      RETURNING id INTO v_id;
    END IF;

    v_out := v_out || jsonb_build_array(jsonb_build_object(
      'object_key', v_key,
      'object_id', v_id
    ));
  END LOOP;

  RETURN v_out;
END;
$$;

CREATE OR REPLACE FUNCTION mark_derived_objects_uploaded(
  p_generation_id UUID,
  p_uploads JSONB
) RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '60s'
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_item JSONB;
  v_object_id UUID;
  v_sha TEXT;
  v_size BIGINT;
  v_row derived_object_index%ROWTYPE;
  v_count INT := 0;
  v_expected INT;
BEGIN
  IF p_uploads IS NULL OR jsonb_typeof(p_uploads) <> 'array' THEN
    RAISE EXCEPTION 'mark_derived_objects_uploaded: p_uploads must be a JSON array';
  END IF;
  v_expected := jsonb_array_length(p_uploads);

  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND OR v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'mark_derived_objects_uploaded: generation % not pending', p_generation_id;
  END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_uploads)
  LOOP
    v_object_id := (v_item->>'object_id')::UUID;
    v_sha := lower(trim(v_item->>'byte_sha256'));
    v_size := (v_item->>'size_bytes')::BIGINT;

    SELECT * INTO v_row FROM derived_object_index WHERE id = v_object_id FOR UPDATE;
    IF NOT FOUND OR v_row.status <> 'pending' OR v_row.generation_id IS DISTINCT FROM p_generation_id THEN
      RAISE EXCEPTION 'mark_derived_objects_uploaded: pending object % not found for generation %', v_object_id, p_generation_id;
    END IF;
    IF v_sha IS NULL OR v_sha !~ '^[a-f0-9]{64}$' OR v_size IS NULL OR v_size <= 0 THEN
      RAISE EXCEPTION 'mark_derived_objects_uploaded: invalid byte hash or size for %', v_object_id;
    END IF;

    UPDATE derived_object_index
    SET byte_sha256 = v_sha,
        size_bytes = v_size,
        upload_verified_at = now()
    WHERE id = v_object_id AND status = 'pending';
    v_count := v_count + 1;
  END LOOP;

  IF v_count <> v_expected THEN
    RAISE EXCEPTION 'mark_derived_objects_uploaded: count mismatch expected % got %', v_expected, v_count;
  END IF;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION stage_latest_derived_observations(
  p_generation_id UUID,
  p_rows JSONB
) RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '60s'
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_item JSONB;
  v_code TEXT;
  v_trade_date DATE;
  v_values JSONB;
  v_digest TEXT;
  v_count INT := 0;
BEGIN
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'stage_latest_derived_observations: p_rows must be a JSON array';
  END IF;

  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND OR v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'stage_latest_derived_observations: generation % not pending', p_generation_id;
  END IF;
  IF v_gen.artifact_profile <> 'snapshot_series_latest' THEN
    RAISE EXCEPTION 'stage_latest_derived_observations: profile % does not allow latest staging', v_gen.artifact_profile;
  END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_rows)
  LOOP
    v_code := trim(v_item->>'instrument_code');
    v_trade_date := (v_item->>'trade_date')::DATE;
    v_values := v_item->'values_json';
    v_digest := lower(trim(v_item->>'logical_digest'));

    IF v_code IS NULL OR v_code = '' OR v_trade_date IS NULL OR v_values IS NULL
       OR v_digest IS NULL OR v_digest !~ '^[a-f0-9]{64}$' THEN
      RAISE EXCEPTION 'stage_latest_derived_observations: invalid row payload';
    END IF;

    INSERT INTO latest_derived_observations_staging (
      generation_id, instrument_code, metric_set_version_id, trade_date,
      values_json, logical_digest, source_run_id
    ) VALUES (
      p_generation_id, v_code, v_gen.metric_set_version_id, v_trade_date,
      v_values, v_digest, v_gen.source_run_id
    )
    ON CONFLICT (generation_id, instrument_code) DO UPDATE
    SET trade_date = EXCLUDED.trade_date,
        values_json = EXCLUDED.values_json,
        logical_digest = EXCLUDED.logical_digest,
        source_run_id = EXCLUDED.source_run_id;
    v_count := v_count + 1;
  END LOOP;

  RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.register_pending_derived_objects(uuid, jsonb)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_derived_objects_uploaded(uuid, jsonb)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.stage_latest_derived_observations(uuid, jsonb)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.register_pending_derived_objects(uuid, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_derived_objects_uploaded(uuid, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.stage_latest_derived_observations(uuid, jsonb) TO service_role;

COMMIT;
