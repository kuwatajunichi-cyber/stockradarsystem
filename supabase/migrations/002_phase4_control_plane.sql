-- Phase 4 control plane (Issue #93). Apply after 001_phase3_control_plane.sql.

CREATE TABLE IF NOT EXISTS monthly_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  monthly_tag TEXT NOT NULL,
  snapshot_date DATE NOT NULL,
  github_run_id BIGINT NOT NULL,
  writer_workflow TEXT NOT NULL DEFAULT 'monthly.yml',
  object_keys JSONB NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'orphan')),
  committed_at_utc TIMESTAMPTZ,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (monthly_tag),
  CONSTRAINT monthly_snapshots_sha256_format
    CHECK (sha256 ~ '^[a-f0-9]{64}$'),
  CONSTRAINT monthly_snapshots_sha256_matches_core
    CHECK ((object_keys->'core'->>'sha256') IS NOT NULL AND sha256 = (object_keys->'core'->>'sha256')),
  CONSTRAINT monthly_snapshots_object_keys_shape CHECK (
    (object_keys->>'monthly_snapshots_schema_version') IS NOT NULL
    AND (object_keys->>'monthly_snapshots_schema_version')::int = 1
    AND object_keys ? 'ipo' AND object_keys ? 'illiquid'
    AND object_keys ? 'core' AND object_keys ? 'manifest'
    AND (object_keys->'ipo'->>'object_key') IS NOT NULL
    AND (object_keys->'ipo'->>'object_key') <> ''
    AND (object_keys->'ipo'->>'object_key') LIKE 'monthly/' || monthly_tag || '/%'
    AND (object_keys->'illiquid'->>'object_key') IS NOT NULL
    AND (object_keys->'illiquid'->>'object_key') <> ''
    AND (object_keys->'illiquid'->>'object_key') LIKE 'monthly/' || monthly_tag || '/%'
    AND (object_keys->'core'->>'object_key') IS NOT NULL
    AND (object_keys->'core'->>'object_key') <> ''
    AND (object_keys->'core'->>'object_key') LIKE 'monthly/' || monthly_tag || '/%'
    AND (object_keys->'manifest'->>'object_key') IS NOT NULL
    AND (object_keys->'manifest'->>'object_key') <> ''
    AND (object_keys->'manifest'->>'object_key') LIKE 'monthly/' || monthly_tag || '/%'
    AND (object_keys->'ipo'->>'sha256') IS NOT NULL AND (object_keys->'ipo'->>'sha256') ~ '^[a-f0-9]{64}$'
    AND (object_keys->'illiquid'->>'sha256') IS NOT NULL AND (object_keys->'illiquid'->>'sha256') ~ '^[a-f0-9]{64}$'
    AND (object_keys->'core'->>'sha256') IS NOT NULL AND (object_keys->'core'->>'sha256') ~ '^[a-f0-9]{64}$'
    AND (object_keys->'manifest'->>'sha256') IS NOT NULL AND (object_keys->'manifest'->>'sha256') ~ '^[a-f0-9]{64}$'
    AND (object_keys->'ipo'->>'size_bytes') IS NOT NULL AND (object_keys->'ipo'->>'size_bytes')::bigint > 0
    AND (object_keys->'illiquid'->>'size_bytes') IS NOT NULL AND (object_keys->'illiquid'->>'size_bytes')::bigint > 0
    AND (object_keys->'core'->>'size_bytes') IS NOT NULL AND (object_keys->'core'->>'size_bytes')::bigint > 0
    AND (object_keys->'manifest'->>'size_bytes') IS NOT NULL AND (object_keys->'manifest'->>'size_bytes')::bigint > 0
    AND (object_keys->'ipo'->>'content_type') IS NOT NULL AND object_keys->'ipo'->>'content_type' = 'text/csv'
    AND (object_keys->'illiquid'->>'content_type') IS NOT NULL AND object_keys->'illiquid'->>'content_type' = 'text/csv'
    AND (object_keys->'core'->>'content_type') IS NOT NULL AND object_keys->'core'->>'content_type' = 'text/csv'
    AND (object_keys->'manifest'->>'content_type') IS NOT NULL AND object_keys->'manifest'->>'content_type' = 'application/json'
  ),
  CONSTRAINT monthly_snapshots_committed_timestamp CHECK (
    (status = 'committed' AND committed_at_utc IS NOT NULL)
    OR status IN ('pending', 'orphan')
  )
);

CREATE INDEX IF NOT EXISTS monthly_snapshots_status_orphan
  ON monthly_snapshots (status) WHERE status = 'orphan';
CREATE INDEX IF NOT EXISTS monthly_snapshots_snapshot_date
  ON monthly_snapshots (snapshot_date DESC, github_run_id DESC);

CREATE TABLE IF NOT EXISTS publish_status (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  workflow TEXT NOT NULL DEFAULT 'daily.yml',
  github_run_id BIGINT NOT NULL,
  run_date DATE NOT NULL,
  logical_kind TEXT NOT NULL
    CHECK (logical_kind IN ('indicators_csv', 'indicators_xlsx')),
  visibility TEXT NOT NULL CHECK (visibility IN ('work', 'paid')),
  object_key TEXT NOT NULL,
  manifest_object_key TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  sha256 TEXT NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
  content_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'orphan', 'failed')),
  committed_at_utc TIMESTAMPTZ,
  degraded_reason TEXT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (run_id, logical_kind),
  CONSTRAINT publish_status_committed_timestamp CHECK (
    (status = 'committed' AND committed_at_utc IS NOT NULL)
    OR status IN ('pending', 'orphan', 'failed')
  ),
  CONSTRAINT publish_status_failed_no_commit_ts CHECK (
    status != 'failed' OR committed_at_utc IS NULL
  )
);

CREATE INDEX IF NOT EXISTS publish_status_run_date ON publish_status (run_date DESC);
CREATE INDEX IF NOT EXISTS publish_status_status_orphan
  ON publish_status (status) WHERE status = 'orphan';
CREATE INDEX IF NOT EXISTS publish_status_status_committed
  ON publish_status (run_id) WHERE status = 'committed';

CREATE OR REPLACE FUNCTION commit_jpx_url_cache(
  p_object_key TEXT,
  p_sha256 TEXT,
  p_size_bytes BIGINT,
  p_writer_workflow TEXT,
  p_source_github_run_id BIGINT,
  p_history_id UUID DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_id UUID;
BEGIN
  IF p_history_id IS NULL THEN
    INSERT INTO cache_index (
      cache_key, cache_kind, object_key, sha256, size_bytes,
      writer_workflow, source_github_run_id, source_ref, status, committed_at_utc
    )
    VALUES (
      'jpx-latest-url', 'fixed', p_object_key, p_sha256, p_size_bytes,
      p_writer_workflow, p_source_github_run_id, 'n/a', 'committed', now()
    )
    ON CONFLICT (cache_key, sha256) WHERE cache_kind = 'fixed'
    DO UPDATE SET status = 'committed', committed_at_utc = now()
    RETURNING id INTO v_id;
  ELSE
    UPDATE cache_index
    SET status = 'committed', committed_at_utc = now()
    WHERE id = p_history_id AND status = 'pending';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'pending cache_index row not found: %', p_history_id;
    END IF;
    v_id := p_history_id;
  END IF;

  INSERT INTO cache_pointers (
    cache_key, object_key, sha256, size_bytes,
    writer_workflow, source_github_run_id, committed_at_utc
  )
  VALUES (
    'jpx-latest-url', p_object_key, p_sha256, p_size_bytes,
    p_writer_workflow, p_source_github_run_id, now()
  )
  ON CONFLICT (cache_key) DO UPDATE SET
    object_key = EXCLUDED.object_key,
    sha256 = EXCLUDED.sha256,
    size_bytes = EXCLUDED.size_bytes,
    source_github_run_id = EXCLUDED.source_github_run_id,
    committed_at_utc = now();

  RETURN v_id;
END;
$$;

GRANT EXECUTE ON FUNCTION commit_jpx_url_cache TO service_role;
