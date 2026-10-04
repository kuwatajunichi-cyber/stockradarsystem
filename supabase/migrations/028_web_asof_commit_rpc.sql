-- Track D web_asof commit: reject snapshot digest, require 2+1 objects, orphan prior as-of.
-- Git 028. Production applied as schema_migrations name 023_web_asof_commit_rpc
-- (version 20261003063535). Do not re-apply.
-- Does not CAS metric_set. Does not mint. P0: service_role execute only.

BEGIN;

CREATE OR REPLACE FUNCTION public.commit_derived_generation(
  p_generation_id UUID,
  p_new_digest TEXT,
  p_expected_old_digest TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '180s'
AS $$
DECLARE
  v_gen public.derived_generation_runs%ROWTYPE;
  v_obj_count INT;
  v_uploaded_count INT;
  v_set_uuid UUID;
  v_current_snapshot_digest TEXT;
  v_current_series_digest TEXT;
  v_cas public.derived_generation_series_cas%ROWTYPE;
  v_expected_delta_kind TEXT;
  v_coordinate_count INT;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_generation_id::text, 0));

  SELECT * INTO v_gen
  FROM public.derived_generation_runs
  WHERE id = p_generation_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION
      'commit_derived_generation: generation % not found', p_generation_id;
  END IF;
  IF v_gen.status = 'committed' THEN
    RETURN p_generation_id;
  END IF;
  IF v_gen.status <> 'pending' THEN
    RAISE EXCEPTION
      'commit_derived_generation: generation % not pending', p_generation_id;
  END IF;

  v_set_uuid := v_gen.metric_set_version_id;
  PERFORM pg_advisory_xact_lock(
    hashtextextended(v_set_uuid::text || ':' || v_gen.trade_date::text, 0)
  );

  IF v_gen.artifact_profile = 'series_only' THEN
    IF p_expected_old_digest IS NOT NULL THEN
      RAISE EXCEPTION
        'commit_derived_generation: p_expected_old_digest is invalid for series_only';
    END IF;
    IF v_gen.mode NOT IN ('series_seed', 'series_repair') THEN
      RAISE EXCEPTION
        'commit_derived_generation: invalid mode for series_only';
    END IF;

    FOR v_cas IN
      SELECT *
      FROM public.derived_generation_series_cas
      WHERE generation_id = p_generation_id
      ORDER BY instrument_code, series_year
    LOOP
      -- Coordinate locks use the existing single-bigint advisory-lock overload.
      PERFORM pg_advisory_xact_lock(
        hashtextextended(
          v_set_uuid::text || ':' || v_cas.instrument_code || ':' ||
          v_cas.series_year::text,
          0
        )
      );

      v_current_series_digest := NULL;
      SELECT d.logical_digest INTO v_current_series_digest
      FROM public.derived_object_index d
      WHERE d.metric_set_version_id = v_set_uuid
        AND d.instrument_code = v_cas.instrument_code
        AND d.series_year = v_cas.series_year
        AND d.object_kind = 'series'
        AND d.status = 'committed'
      FOR UPDATE;

      IF v_cas.prior_absent AND FOUND THEN
        RAISE EXCEPTION
          'commit_derived_generation: series CAS expected absent for %/%',
          v_cas.instrument_code, v_cas.series_year;
      END IF;
      IF NOT v_cas.prior_absent
         AND (
           NOT FOUND
           OR v_current_series_digest IS DISTINCT FROM
              v_cas.expected_prior_logical_digest
         ) THEN
        RAISE EXCEPTION
          'commit_derived_generation: series CAS digest mismatch for %/%',
          v_cas.instrument_code, v_cas.series_year;
      END IF;
    END LOOP;

    SELECT count(*) INTO v_coordinate_count
    FROM public.derived_generation_series_cas
    WHERE generation_id = p_generation_id;
    IF v_coordinate_count = 0 THEN
      RAISE EXCEPTION
        'commit_derived_generation: series_only requires CAS coordinates';
    END IF;
    IF (
      SELECT count(*)
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind = 'series'
    ) <> v_coordinate_count OR (
      SELECT count(*)
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind = 'series_manifest'
    ) <> v_coordinate_count THEN
      RAISE EXCEPTION
        'commit_derived_generation: series objects do not match CAS coordinates';
    END IF;

    v_expected_delta_kind := CASE v_gen.mode
      WHEN 'series_seed' THEN 'series_seed_delta'
      ELSE 'series_repair_delta'
    END;
    IF (
      SELECT count(*)
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind = v_expected_delta_kind
    ) <> 1 THEN
      RAISE EXCEPTION
        'commit_derived_generation: series_only requires exactly one delta';
    END IF;
    IF EXISTS (
      SELECT 1
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind NOT IN (
          'series', 'series_manifest', v_expected_delta_kind
        )
    ) THEN
      RAISE EXCEPTION
        'commit_derived_generation: invalid object kind for series_only';
    END IF;
  ELSIF v_gen.artifact_profile = 'web_asof' THEN
    IF p_expected_old_digest IS NOT NULL THEN
      RAISE EXCEPTION
        'commit_derived_generation: p_expected_old_digest is invalid for web_asof';
    END IF;
    IF EXISTS (
      SELECT 1
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind NOT IN ('web_asof_bundle', 'web_asof_manifest')
    ) THEN
      RAISE EXCEPTION
        'commit_derived_generation: invalid object kind for web_asof';
    END IF;
    IF (
      SELECT count(*)
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind = 'web_asof_bundle'
    ) <> 2 OR (
      SELECT count(*)
      FROM public.derived_object_index d
      WHERE d.generation_id = p_generation_id
        AND d.status = 'pending'
        AND d.object_kind = 'web_asof_manifest'
    ) <> 1 THEN
      RAISE EXCEPTION
        'commit_derived_generation: web_asof requires two bundles and one manifest';
    END IF;
  ELSE
    IF p_expected_old_digest IS NOT NULL THEN
      SELECT d.logical_digest INTO v_current_snapshot_digest
      FROM public.derived_object_index d
      WHERE d.metric_set_version_id = v_set_uuid
        AND d.trade_date = v_gen.trade_date
        AND d.object_kind = 'snapshot'
        AND d.status = 'committed'
      ORDER BY d.committed_at_utc DESC NULLS LAST
      LIMIT 1;

      IF v_current_snapshot_digest IS NULL THEN
        RAISE EXCEPTION
          'commit_derived_generation: expected_old_digest provided but no committed snapshot';
      END IF;
      IF v_current_snapshot_digest <> p_expected_old_digest THEN
        RAISE EXCEPTION
          'commit_derived_generation: expected_old_digest mismatch (current=% expected=%)',
          v_current_snapshot_digest, p_expected_old_digest;
      END IF;
    END IF;
  END IF;

  IF v_gen.declared_new_digest IS NOT NULL
     AND p_new_digest IS DISTINCT FROM v_gen.declared_new_digest THEN
    RAISE EXCEPTION 'commit_derived_generation: new_digest mismatch';
  END IF;

  SELECT count(*) INTO v_obj_count
  FROM public.derived_object_index
  WHERE generation_id = p_generation_id AND status = 'pending';

  SELECT count(*) INTO v_uploaded_count
  FROM public.derived_object_index
  WHERE generation_id = p_generation_id
    AND status = 'pending'
    AND upload_verified_at IS NOT NULL
    AND byte_sha256 IS NOT NULL
    AND size_bytes IS NOT NULL;

  IF v_gen.expected_object_count IS NULL THEN
    RAISE EXCEPTION
      'commit_derived_generation: expected_object_count is required';
  END IF;
  IF v_obj_count <> v_gen.expected_object_count THEN
    RAISE EXCEPTION
      'commit_derived_generation: expected object count mismatch';
  END IF;
  IF v_obj_count = 0 OR v_obj_count <> v_uploaded_count THEN
    RAISE EXCEPTION
      'commit_derived_generation: not all objects uploaded';
  END IF;

  IF v_gen.expected_object_set_digest IS NULL THEN
    RAISE EXCEPTION
      'commit_derived_generation: expected_object_set_digest is required';
  END IF;
  PERFORM 1 FROM (
    SELECT encode(
      sha256(convert_to(string_agg(object_key, E'\n' ORDER BY object_key), 'UTF8')),
      'hex'
    ) AS digest
    FROM public.derived_object_index
    WHERE generation_id = p_generation_id AND status = 'pending'
  ) AS computed
  WHERE computed.digest <> v_gen.expected_object_set_digest;
  IF FOUND THEN
    RAISE EXCEPTION
      'commit_derived_generation: object_set_digest mismatch';
  END IF;

  IF v_gen.artifact_profile = 'snapshot_series_latest' THEN
    IF NOT EXISTS (
      SELECT 1
      FROM public.latest_derived_observations_staging
      WHERE generation_id = p_generation_id
    ) THEN
      RAISE EXCEPTION
        'commit_derived_generation: latest staging required for profile';
    END IF;
    IF v_gen.expected_latest_set_digest IS NOT NULL THEN
      PERFORM 1 FROM (
        SELECT encode(
          sha256(
            convert_to(
              string_agg(instrument_code, E'\n' ORDER BY instrument_code),
              'UTF8'
            )
          ),
          'hex'
        ) AS digest
        FROM public.latest_derived_observations_staging
        WHERE generation_id = p_generation_id
      ) AS computed
      WHERE computed.digest <> v_gen.expected_latest_set_digest;
      IF FOUND THEN
        RAISE EXCEPTION
          'commit_derived_generation: latest_set_digest mismatch';
      END IF;
    END IF;
  END IF;

  IF v_gen.artifact_profile = 'series_only' THEN
    -- Only coordinates registered with prior_absent=false replace an old
    -- active series.  Keep the old generation_id for audit.
    UPDATE public.derived_object_index d
    SET status = 'superseded'
    FROM public.derived_generation_series_cas c
    WHERE c.generation_id = p_generation_id
      AND NOT c.prior_absent
      AND d.metric_set_version_id = v_set_uuid
      AND d.instrument_code = c.instrument_code
      AND d.series_year = c.series_year
      AND d.object_kind IN ('series', 'series_manifest')
      AND d.status = 'committed'
      AND d.generation_id IS DISTINCT FROM p_generation_id;
  ELSE
    -- Preserve the 009 Daily/backfill/reconcile behavior.  This block is
    -- intentionally not run for series_only.
    IF v_gen.artifact_profile = 'web_asof' THEN
      UPDATE public.derived_object_index d
      SET status = 'orphan'
      WHERE d.object_kind IN ('web_asof_bundle', 'web_asof_manifest')
        AND d.metric_set_version_id = v_gen.metric_set_version_id
        AND d.trade_date = v_gen.trade_date
        AND d.status = 'committed'
        AND d.generation_id IS DISTINCT FROM p_generation_id;
    END IF;

    IF v_gen.artifact_profile IN (
      'snapshot_only', 'snapshot_series', 'snapshot_series_latest'
    ) THEN
      UPDATE public.derived_object_index d
      SET status = 'orphan'
      WHERE d.object_kind IN ('snapshot', 'snapshot_manifest')
        AND d.metric_set_version_id = v_gen.metric_set_version_id
        AND d.trade_date = v_gen.trade_date
        AND d.status = 'committed'
        AND d.generation_id IS DISTINCT FROM p_generation_id;
    END IF;

    IF v_gen.artifact_profile IN (
      'snapshot_series', 'snapshot_series_latest'
    ) THEN
      UPDATE public.derived_object_index d
      SET status = 'orphan'
      WHERE d.object_kind IN ('series', 'series_manifest')
        AND d.metric_set_version_id = v_gen.metric_set_version_id
        AND d.status = 'committed'
        AND d.generation_id IS DISTINCT FROM p_generation_id
        AND EXISTS (
          SELECT 1
          FROM public.derived_object_index cur
          WHERE cur.generation_id = p_generation_id
            AND cur.object_kind = 'series'
            AND cur.instrument_code = d.instrument_code
            AND cur.series_year = d.series_year
        );
    END IF;
  END IF;

  -- Includes the create-only delta.  Delta rows are never superseded here.
  UPDATE public.derived_object_index
  SET status = 'committed', committed_at_utc = now()
  WHERE generation_id = p_generation_id AND status = 'pending';

  IF v_gen.artifact_profile = 'snapshot_series_latest' THEN
    INSERT INTO public.latest_derived_observations (
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
    FROM public.latest_derived_observations_staging s
    WHERE s.generation_id = p_generation_id
    ON CONFLICT (instrument_code, metric_set_version_id) DO UPDATE SET
      trade_date = EXCLUDED.trade_date,
      values_json = EXCLUDED.values_json,
      logical_digest = EXCLUDED.logical_digest,
      source_run_id = EXCLUDED.source_run_id,
      generation_id = EXCLUDED.generation_id,
      updated_at_utc = now()
    WHERE public.latest_derived_observations.trade_date <= EXCLUDED.trade_date;
  END IF;

  DELETE FROM public.latest_derived_observations_staging
  WHERE generation_id = p_generation_id;

  UPDATE public.derived_generation_runs
  SET status = 'committed',
      new_digest = p_new_digest,
      committed_at_utc = now(),
      updated_at_utc = now()
  WHERE id = p_generation_id;

  RETURN p_generation_id;
END;
$$;

REVOKE ALL ON FUNCTION public.commit_derived_generation(uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text, text)
  TO service_role;

COMMIT;
