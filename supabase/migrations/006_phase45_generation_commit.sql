-- Phase 4.5 derived generation commit (Issue #93).
-- Apply after 005_phase45_metric_registry_hardening.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS derived_generation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metric_set_version_id UUID NOT NULL REFERENCES metric_set_versions(id),
  trade_date DATE NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('normal', 'replay', 'backfill', 'reconcile')),
  artifact_profile TEXT NOT NULL CHECK (
    artifact_profile IN ('snapshot_only', 'snapshot_series', 'snapshot_series_latest')
  ),
  expected_old_digest TEXT CHECK (
    expected_old_digest IS NULL OR expected_old_digest ~ '^[a-f0-9]{64}$'
  ),
  declared_new_digest TEXT CHECK (
    declared_new_digest IS NULL OR declared_new_digest ~ '^[a-f0-9]{64}$'
  ),
  new_digest TEXT CHECK (new_digest IS NULL OR new_digest ~ '^[a-f0-9]{64}$'),
  expected_object_count INT CHECK (expected_object_count IS NULL OR expected_object_count >= 0),
  expected_object_set_digest TEXT CHECK (
    expected_object_set_digest IS NULL OR expected_object_set_digest ~ '^[a-f0-9]{64}$'
  ),
  expected_latest_set_digest TEXT CHECK (
    expected_latest_set_digest IS NULL OR expected_latest_set_digest ~ '^[a-f0-9]{64}$'
  ),
  repository TEXT NOT NULL,
  workflow TEXT NOT NULL,
  github_run_id BIGINT NOT NULL,
  run_attempt INT NOT NULL DEFAULT 1,
  writer_workflow TEXT NOT NULL,
  source_run_id UUID REFERENCES runs(id),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'failed')),
  heartbeat_at TIMESTAMPTZ,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  committed_at_utc TIMESTAMPTZ,
  failed_at_utc TIMESTAMPTZ,
  CONSTRAINT derived_generation_committed_ts CHECK (
    (status = 'committed' AND committed_at_utc IS NOT NULL)
    OR (status = 'failed' AND failed_at_utc IS NOT NULL)
    OR status = 'pending'
  )
);

-- Source identity: (repository, workflow, github_run_id, set_uuid, trade_date, mode); run_attempt excluded.
CREATE UNIQUE INDEX IF NOT EXISTS derived_generation_runs_source_identity
  ON derived_generation_runs (
    repository, workflow, github_run_id, metric_set_version_id, trade_date, mode
  );

CREATE INDEX IF NOT EXISTS derived_generation_runs_status_heartbeat
  ON derived_generation_runs (status, heartbeat_at)
  WHERE status = 'pending';

ALTER TABLE derived_object_index
  ADD COLUMN IF NOT EXISTS generation_id UUID REFERENCES derived_generation_runs(id),
  ADD COLUMN IF NOT EXISTS upload_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS purged_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_generation_coordinate
  ON derived_object_index (
    generation_id,
    object_kind,
    trade_date,
    instrument_code,
    series_year
  )
  WHERE generation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_snapshot_coordinate
  ON derived_object_index (metric_set_version_id, trade_date)
  WHERE object_kind = 'snapshot' AND status = 'committed';

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_series_coordinate
  ON derived_object_index (metric_set_version_id, instrument_code, series_year)
  WHERE object_kind = 'series' AND status = 'committed';

CREATE TABLE IF NOT EXISTS latest_derived_observations_staging (
  generation_id UUID NOT NULL REFERENCES derived_generation_runs(id) ON DELETE CASCADE,
  instrument_code TEXT NOT NULL,
  metric_set_version_id UUID NOT NULL REFERENCES metric_set_versions(id),
  trade_date DATE NOT NULL,
  values_json JSONB NOT NULL,
  logical_digest TEXT NOT NULL CHECK (logical_digest ~ '^[a-f0-9]{64}$'),
  source_run_id UUID REFERENCES runs(id),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (generation_id, instrument_code)
);

ALTER TABLE latest_derived_observations
  ADD COLUMN IF NOT EXISTS generation_id UUID REFERENCES derived_generation_runs(id);

CREATE OR REPLACE FUNCTION begin_derived_generation(
  p_metric_set_version_id UUID,
  p_trade_date DATE,
  p_mode TEXT,
  p_artifact_profile TEXT,
  p_repository TEXT,
  p_workflow TEXT,
  p_github_run_id BIGINT,
  p_run_attempt INT,
  p_writer_workflow TEXT,
  p_source_run_id UUID,
  p_expected_old_digest TEXT,
  p_declared_new_digest TEXT,
  p_expected_object_count INT,
  p_expected_object_set_digest TEXT,
  p_expected_latest_set_digest TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_existing derived_generation_runs%ROWTYPE;
  v_id UUID;
BEGIN
  SELECT * INTO v_existing
  FROM derived_generation_runs
  WHERE repository = p_repository
    AND workflow = p_workflow
    AND github_run_id = p_github_run_id
    AND metric_set_version_id = p_metric_set_version_id
    AND trade_date = p_trade_date
    AND mode = p_mode
  FOR UPDATE;

  IF FOUND THEN
    IF v_existing.status = 'failed' THEN
      RAISE EXCEPTION 'derived generation failed; new source identity required (set_uuid=%)', p_metric_set_version_id;
    END IF;
    IF v_existing.status = 'committed' THEN
      IF v_existing.artifact_profile IS DISTINCT FROM p_artifact_profile
         OR v_existing.expected_object_count IS DISTINCT FROM p_expected_object_count
         OR v_existing.expected_object_set_digest IS DISTINCT FROM p_expected_object_set_digest
         OR v_existing.expected_latest_set_digest IS DISTINCT FROM p_expected_latest_set_digest
         OR v_existing.declared_new_digest IS DISTINCT FROM p_declared_new_digest
         OR (p_expected_old_digest IS NOT NULL AND v_existing.expected_old_digest IS DISTINCT FROM p_expected_old_digest) THEN
        RAISE EXCEPTION 'derived generation payload mismatch for committed source identity (set_uuid=%)', p_metric_set_version_id;
      END IF;
      RETURN v_existing.id;
    END IF;
    IF v_existing.artifact_profile IS DISTINCT FROM p_artifact_profile
       OR v_existing.expected_object_count IS DISTINCT FROM p_expected_object_count
       OR v_existing.expected_object_set_digest IS DISTINCT FROM p_expected_object_set_digest
       OR v_existing.expected_latest_set_digest IS DISTINCT FROM p_expected_latest_set_digest
       OR v_existing.declared_new_digest IS DISTINCT FROM p_declared_new_digest
       OR (p_expected_old_digest IS NOT NULL AND v_existing.expected_old_digest IS DISTINCT FROM p_expected_old_digest) THEN
      RAISE EXCEPTION 'derived generation payload mismatch for source identity (set_uuid=%)', p_metric_set_version_id;
    END IF;
    UPDATE derived_generation_runs
    SET heartbeat_at = now(), updated_at_utc = now(), run_attempt = COALESCE(p_run_attempt, run_attempt)
    WHERE id = v_existing.id;
    RETURN v_existing.id;
  END IF;

  INSERT INTO derived_generation_runs (
    metric_set_version_id, trade_date, mode, artifact_profile,
    expected_old_digest, declared_new_digest,
    expected_object_count, expected_object_set_digest, expected_latest_set_digest,
    repository, workflow, github_run_id, run_attempt,
    writer_workflow, source_run_id, status, heartbeat_at
  ) VALUES (
    p_metric_set_version_id, p_trade_date, p_mode, p_artifact_profile,
    p_expected_old_digest, p_declared_new_digest,
    p_expected_object_count, p_expected_object_set_digest, p_expected_latest_set_digest,
    p_repository, p_workflow, p_github_run_id, COALESCE(p_run_attempt, 1),
    p_writer_workflow, p_source_run_id, 'pending', now()
  )
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION register_pending_derived_object(
  p_generation_id UUID,
  p_object_kind TEXT,
  p_object_key TEXT,
  p_logical_digest TEXT,
  p_layer1_input_fingerprint TEXT,
  p_writer_workflow TEXT,
  p_trade_date DATE,
  p_instrument_code TEXT,
  p_series_year INT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_row derived_object_index%ROWTYPE;
  v_id UUID;
BEGIN
  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND OR v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'register_pending_derived_object: generation % not pending', p_generation_id;
  END IF;

  SELECT * INTO v_row
  FROM derived_object_index
  WHERE generation_id = p_generation_id
    AND object_kind = p_object_kind
    AND trade_date IS NOT DISTINCT FROM p_trade_date
    AND instrument_code IS NOT DISTINCT FROM p_instrument_code
    AND series_year IS NOT DISTINCT FROM p_series_year
  FOR UPDATE;

  IF FOUND THEN
    IF v_row.logical_digest = p_logical_digest THEN
      RETURN v_row.id;
    END IF;
    RAISE EXCEPTION 'register_pending_derived_object: coordinate conflict for generation %', p_generation_id;
  END IF;

  INSERT INTO derived_object_index (
    object_kind, metric_set_version_id, trade_date, instrument_code, series_year,
    object_key, logical_digest, layer1_input_fingerprint, writer_workflow,
    generation_id, status
  ) VALUES (
    p_object_kind, v_gen.metric_set_version_id, p_trade_date, p_instrument_code, p_series_year,
    p_object_key, p_logical_digest, p_layer1_input_fingerprint, p_writer_workflow,
    p_generation_id, 'pending'
  )
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION mark_derived_object_uploaded(
  p_object_id UUID,
  p_byte_sha256 TEXT,
  p_size_bytes BIGINT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_row derived_object_index%ROWTYPE;
BEGIN
  SELECT * INTO v_row FROM derived_object_index WHERE id = p_object_id FOR UPDATE;
  IF NOT FOUND OR v_row.status <> 'pending' THEN
    RAISE EXCEPTION 'mark_derived_object_uploaded: pending object % not found', p_object_id;
  END IF;
  IF p_byte_sha256 !~ '^[a-f0-9]{64}$' OR p_size_bytes IS NULL OR p_size_bytes <= 0 THEN
    RAISE EXCEPTION 'mark_derived_object_uploaded: invalid byte hash or size for %', p_object_id;
  END IF;
  UPDATE derived_object_index
  SET byte_sha256 = p_byte_sha256,
      size_bytes = p_size_bytes,
      upload_verified_at = now()
  WHERE id = p_object_id AND status = 'pending';
  RETURN p_object_id;
END;
$$;

CREATE OR REPLACE FUNCTION heartbeat_derived_generation(p_generation_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE derived_generation_runs
  SET heartbeat_at = now(), updated_at_utc = now()
  WHERE id = p_generation_id AND status = 'pending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'heartbeat_derived_generation: pending generation % not found', p_generation_id;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION commit_derived_generation(
  p_generation_id UUID,
  p_new_digest TEXT
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

  IF v_gen.expected_object_count IS NOT NULL AND v_obj_count <> v_gen.expected_object_count THEN
    RAISE EXCEPTION 'commit_derived_generation: expected object count mismatch';
  END IF;
  IF v_obj_count = 0 OR v_obj_count <> v_uploaded_count THEN
    RAISE EXCEPTION 'commit_derived_generation: not all objects uploaded';
  END IF;

  IF v_gen.expected_object_set_digest IS NOT NULL THEN
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
    WHERE d.object_kind = 'snapshot'
      AND d.metric_set_version_id = v_gen.metric_set_version_id
      AND d.trade_date = v_gen.trade_date
      AND d.status = 'committed'
      AND d.generation_id IS DISTINCT FROM p_generation_id;
  END IF;

  IF v_gen.artifact_profile IN ('snapshot_series', 'snapshot_series_latest') THEN
    UPDATE derived_object_index d
    SET status = 'orphan'
    WHERE d.object_kind = 'series'
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

  UPDATE derived_generation_runs
  SET status = 'committed',
      new_digest = p_new_digest,
      committed_at_utc = now(),
      updated_at_utc = now()
  WHERE id = p_generation_id;

  RETURN p_generation_id;
END;
$$;

CREATE OR REPLACE FUNCTION mark_derived_generation_failed(p_generation_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE derived_generation_runs
  SET status = 'failed', failed_at_utc = now(), updated_at_utc = now()
  WHERE id = p_generation_id AND status = 'pending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'mark_derived_generation_failed: pending generation % not found', p_generation_id;
  END IF;
  UPDATE derived_object_index
  SET status = 'orphan'
  WHERE generation_id = p_generation_id AND status = 'pending';
END;
$$;

CREATE OR REPLACE FUNCTION list_stale_derived_generations(p_stale_before TIMESTAMPTZ)
RETURNS SETOF derived_generation_runs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT *
  FROM derived_generation_runs
  WHERE status = 'pending'
    AND (
      heartbeat_at IS NULL
      OR heartbeat_at < p_stale_before
    );
$$;

CREATE OR REPLACE FUNCTION mark_orphan_object_purged(p_object_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE derived_object_index
  SET purged_at = now()
  WHERE id = p_object_id AND status = 'orphan' AND purged_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'mark_orphan_object_purged: orphan object % not found', p_object_id;
  END IF;
  RETURN p_object_id;
END;
$$;

REVOKE ALL ON FUNCTION public.commit_derived_object(uuid, text, bigint, text)
  FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL ON FUNCTION public.begin_derived_generation(
  uuid, date, text, text, text, text, bigint, int, text, uuid,
  text, text, int, text, text
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.register_pending_derived_object(
  uuid, text, text, text, text, text, date, text, int
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_derived_object_uploaded(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.heartbeat_derived_generation(uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.commit_derived_generation(uuid, text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_derived_generation_failed(uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.list_stale_derived_generations(timestamptz)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_orphan_object_purged(uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.begin_derived_generation(
  uuid, date, text, text, text, text, bigint, int, text, uuid,
  text, text, int, text, text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.register_pending_derived_object(
  uuid, text, text, text, text, text, date, text, int
) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_derived_object_uploaded(uuid, text, bigint)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_derived_generation(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_derived_generation_failed(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.list_stale_derived_generations(timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_orphan_object_purged(uuid) TO service_role;

ALTER TABLE public.derived_generation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.latest_derived_observations_staging ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.derived_generation_runs FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.latest_derived_observations_staging FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT ON TABLE public.derived_generation_runs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.latest_derived_observations_staging TO service_role;

COMMIT;
