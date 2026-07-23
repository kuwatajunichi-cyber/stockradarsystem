-- Phase 4.5 metric registry (Issue #93). Apply after 003_p0_control_plane_hardening.sql.

CREATE TABLE IF NOT EXISTS metric_definitions (
  metric_key TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  value_type TEXT NOT NULL CHECK (value_type IN ('float', 'int', 'bool', 'string')),
  unit TEXT,
  description TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'active'
    CHECK (lifecycle IN ('active', 'deprecated', 'retired')),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metric_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metric_key TEXT NOT NULL REFERENCES metric_definitions(metric_key),
  version_label TEXT NOT NULL,
  parameters JSONB NOT NULL,
  required_inputs JSONB NOT NULL,
  min_history_days INT NOT NULL CHECK (min_history_days >= 0),
  missing_policy JSONB NOT NULL,
  definition_canonical JSONB NOT NULL,
  definition_fingerprint TEXT NOT NULL CHECK (definition_fingerprint ~ '^[a-f0-9]{64}$'),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (metric_key, definition_fingerprint)
);

CREATE INDEX IF NOT EXISTS metric_versions_metric_key_created
  ON metric_versions (metric_key, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS metric_set_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  set_key TEXT NOT NULL UNIQUE,
  lifecycle_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (lifecycle_status IN ('draft', 'shadow', 'active', 'retired')),
  set_fingerprint TEXT NOT NULL CHECK (set_fingerprint ~ '^[a-f0-9]{64}$'),
  source_run_id UUID REFERENCES runs(id),
  writer_workflow TEXT NOT NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS metric_set_versions_lifecycle
  ON metric_set_versions (lifecycle_status);

CREATE TABLE IF NOT EXISTS metric_set_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metric_set_version_id UUID NOT NULL REFERENCES metric_set_versions(id) ON DELETE CASCADE,
  metric_version_id UUID NOT NULL REFERENCES metric_versions(id),
  ordinal INT NOT NULL CHECK (ordinal >= 0),
  UNIQUE (metric_set_version_id, ordinal),
  UNIQUE (metric_set_version_id, metric_version_id)
);

CREATE TABLE IF NOT EXISTS active_metric_set (
  pointer_key TEXT PRIMARY KEY DEFAULT 'default',
  metric_set_version_id UUID REFERENCES metric_set_versions(id),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  writer_workflow TEXT,
  source_github_run_id BIGINT
);

-- Seed default pointer so concurrent first activations serialize on FOR UPDATE.
INSERT INTO active_metric_set (pointer_key, metric_set_version_id, updated_at_utc)
VALUES ('default', NULL, now())
ON CONFLICT (pointer_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS derived_object_index (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  object_kind TEXT NOT NULL CHECK (object_kind IN ('snapshot', 'series')),
  metric_set_version_id UUID NOT NULL REFERENCES metric_set_versions(id),
  trade_date DATE,
  instrument_code TEXT,
  series_year INT CHECK (series_year BETWEEN 1900 AND 2100),
  object_key TEXT NOT NULL,
  logical_digest TEXT NOT NULL CHECK (logical_digest ~ '^[a-f0-9]{64}$'),
  byte_sha256 TEXT CHECK (byte_sha256 IS NULL OR byte_sha256 ~ '^[a-f0-9]{64}$'),
  size_bytes BIGINT CHECK (size_bytes > 0),
  layer1_input_fingerprint TEXT,
  source_run_id UUID REFERENCES runs(id),
  writer_workflow TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'orphan')),
  committed_at_utc TIMESTAMPTZ,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT derived_object_shape CHECK (
    (object_kind = 'snapshot' AND trade_date IS NOT NULL AND instrument_code IS NULL AND series_year IS NULL)
    OR (object_kind = 'series' AND instrument_code IS NOT NULL AND series_year IS NOT NULL AND trade_date IS NULL)
  ),
  CONSTRAINT derived_object_committed_ts CHECK (
    (status = 'committed' AND committed_at_utc IS NOT NULL) OR status IN ('pending', 'orphan')
  ),
  CONSTRAINT derived_object_snapshot_layer1_fingerprint CHECK (
    object_kind <> 'snapshot'
    OR (
      layer1_input_fingerprint IS NOT NULL
      AND layer1_input_fingerprint ~ '^[a-f0-9]{64}$'
    )
  )
);

CREATE INDEX IF NOT EXISTS derived_object_index_status_orphan
  ON derived_object_index (status) WHERE status = 'orphan';

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_pending_object_key
  ON derived_object_index (object_key) WHERE status = 'pending';

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_snapshot_committed_object_key
  ON derived_object_index (object_key)
  WHERE object_kind = 'snapshot' AND status = 'committed';

CREATE TABLE IF NOT EXISTS latest_derived_observations (
  instrument_code TEXT NOT NULL,
  metric_set_version_id UUID NOT NULL REFERENCES metric_set_versions(id),
  trade_date DATE NOT NULL,
  values_json JSONB NOT NULL,
  logical_digest TEXT NOT NULL CHECK (logical_digest ~ '^[a-f0-9]{64}$'),
  source_run_id UUID REFERENCES runs(id),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (instrument_code, metric_set_version_id)
);

CREATE INDEX IF NOT EXISTS latest_derived_observations_set_date
  ON latest_derived_observations (metric_set_version_id, trade_date DESC);

CREATE OR REPLACE FUNCTION commit_derived_object(
  p_history_id UUID,
  p_logical_digest TEXT,
  p_size_bytes BIGINT,
  p_byte_sha256 TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_row derived_object_index%ROWTYPE;
BEGIN
  SELECT * INTO v_row FROM derived_object_index WHERE id = p_history_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'derived_object_index pending row not found: %', p_history_id;
  END IF;
  IF v_row.status = 'committed' THEN
    IF v_row.logical_digest = p_logical_digest AND v_row.size_bytes = p_size_bytes THEN
      RETURN p_history_id;
    END IF;
    RAISE EXCEPTION 'derived_object commit conflict for %', p_history_id;
  END IF;
  IF v_row.object_kind = 'snapshot' THEN
    IF v_row.layer1_input_fingerprint IS NULL
       OR v_row.layer1_input_fingerprint !~ '^[a-f0-9]{64}$' THEN
      RAISE EXCEPTION 'snapshot commit requires SHA-shaped layer1_input_fingerprint';
    END IF;
  END IF;
  UPDATE derived_object_index
  SET status = 'committed',
      logical_digest = p_logical_digest,
      size_bytes = p_size_bytes,
      byte_sha256 = p_byte_sha256,
      committed_at_utc = now()
  WHERE id = p_history_id AND status = 'pending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'pending derived_object_index row not found: %', p_history_id;
  END IF;
  IF v_row.object_kind = 'series' THEN
    UPDATE derived_object_index
    SET status = 'orphan'
    WHERE object_key = v_row.object_key
      AND object_kind = 'series'
      AND status = 'committed'
      AND id <> p_history_id;
  END IF;
  RETURN p_history_id;
END;
$$;

CREATE OR REPLACE FUNCTION transition_metric_set(
  p_set_id UUID,
  p_from_status TEXT,
  p_to_status TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF (p_from_status, p_to_status) NOT IN (
    ('draft', 'shadow'),
    ('shadow', 'draft'),
    ('draft', 'retired'),
    ('shadow', 'retired')
  ) THEN
    RAISE EXCEPTION
      'metric_set transition not allowed: % -> % (activation requires activate_metric_set_cas)',
      p_from_status, p_to_status;
  END IF;
  UPDATE metric_set_versions
  SET lifecycle_status = p_to_status
  WHERE id = p_set_id AND lifecycle_status = p_from_status;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'metric_set transition denied: % -> %', p_from_status, p_to_status;
  END IF;
  RETURN p_set_id;
END;
$$;

CREATE OR REPLACE FUNCTION activate_metric_set_cas(
  p_expected_set_id UUID,
  p_new_set_id UUID,
  p_writer_workflow TEXT,
  p_source_github_run_id BIGINT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_current UUID;
BEGIN
  SELECT metric_set_version_id INTO v_current
  FROM active_metric_set WHERE pointer_key = 'default' FOR UPDATE;
  IF v_current IS DISTINCT FROM p_expected_set_id THEN
    RAISE EXCEPTION 'active_metric_set_cas_conflict: expected % current %', p_expected_set_id, v_current;
  END IF;
  IF v_current = p_new_set_id THEN
    UPDATE active_metric_set SET
      writer_workflow = p_writer_workflow,
      source_github_run_id = p_source_github_run_id,
      updated_at_utc = now()
    WHERE pointer_key = 'default';
    RETURN p_new_set_id;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM metric_set_versions
    WHERE id = p_new_set_id AND lifecycle_status IN ('shadow', 'retired')
  ) THEN
    RAISE EXCEPTION 'activate_metric_set_cas: set % not activatable (requires shadow or retired)', p_new_set_id;
  END IF;
  UPDATE metric_set_versions SET lifecycle_status = 'retired'
  WHERE lifecycle_status = 'active' AND id IS DISTINCT FROM p_new_set_id;
  UPDATE metric_set_versions SET lifecycle_status = 'active'
  WHERE id = p_new_set_id AND lifecycle_status IN ('shadow', 'retired');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'activate_metric_set_cas: failed to activate %', p_new_set_id;
  END IF;
  INSERT INTO active_metric_set (pointer_key, metric_set_version_id, writer_workflow, source_github_run_id, updated_at_utc)
  VALUES ('default', p_new_set_id, p_writer_workflow, p_source_github_run_id, now())
  ON CONFLICT (pointer_key) DO UPDATE SET
    metric_set_version_id = EXCLUDED.metric_set_version_id,
    writer_workflow = EXCLUDED.writer_workflow,
    source_github_run_id = EXCLUDED.source_github_run_id,
    updated_at_utc = now();
  RETURN p_new_set_id;
END;
$$;

REVOKE ALL ON FUNCTION commit_derived_object(uuid, text, bigint, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION transition_metric_set(uuid, text, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION activate_metric_set_cas(uuid, uuid, text, bigint) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION commit_derived_object TO service_role;
GRANT EXECUTE ON FUNCTION transition_metric_set TO service_role;
GRANT EXECUTE ON FUNCTION activate_metric_set_cas TO service_role;
