-- Phase 3 control plane (Issue #93). Apply via Supabase SQL editor or migration tooling.

CREATE TABLE IF NOT EXISTS runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow TEXT NOT NULL,
  github_run_id BIGINT NOT NULL,
  run_date DATE,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled')),
  started_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at_utc TIMESTAMPTZ,
  degraded_reason TEXT,
  UNIQUE (workflow, github_run_id)
);

CREATE TABLE IF NOT EXISTS artifact_index (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  source_kind TEXT NOT NULL DEFAULT 'artifact',
  source_name TEXT NOT NULL,
  object_key TEXT NOT NULL,
  size_bytes BIGINT,
  sha256 TEXT NOT NULL,
  content_type TEXT,
  retention_policy TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'orphan')),
  committed_at_utc TIMESTAMPTZ,
  UNIQUE (run_id, source_name)
);

CREATE INDEX IF NOT EXISTS artifact_index_status_orphan
  ON artifact_index (status) WHERE status = 'orphan';

CREATE TABLE IF NOT EXISTS cache_index (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cache_key TEXT NOT NULL,
  cache_kind TEXT NOT NULL CHECK (cache_kind IN ('fixed', 'patched')),
  object_key TEXT,
  object_keys JSONB,
  size_bytes BIGINT,
  sha256 TEXT NOT NULL,
  writer_workflow TEXT NOT NULL,
  source_github_run_id BIGINT,
  source_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'committed', 'orphan')),
  replay_save_skipped BOOLEAN NOT NULL DEFAULT false,
  committed_at_utc TIMESTAMPTZ,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cache_index_object_shape CHECK (
    (cache_kind = 'fixed' AND object_key IS NOT NULL AND object_keys IS NULL)
    OR (cache_kind = 'patched' AND object_keys IS NOT NULL AND object_key IS NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS cache_index_fixed_history
  ON cache_index (cache_key, sha256) WHERE cache_kind = 'fixed';

CREATE UNIQUE INDEX IF NOT EXISTS cache_index_patched_key
  ON cache_index (cache_key) WHERE cache_kind = 'patched';

CREATE INDEX IF NOT EXISTS cache_index_status_orphan
  ON cache_index (status) WHERE status = 'orphan';

CREATE TABLE IF NOT EXISTS cache_pointers (
  cache_key TEXT PRIMARY KEY,
  object_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  writer_workflow TEXT NOT NULL,
  source_github_run_id BIGINT NOT NULL,
  committed_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION commit_fixed_cache(
  p_cache_key TEXT,
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
DECLARE
  v_id UUID;
BEGIN
  IF p_history_id IS NULL THEN
    INSERT INTO cache_index (
      cache_key, cache_kind, object_key, sha256, size_bytes,
      writer_workflow, source_github_run_id, source_ref, status, committed_at_utc
    )
    VALUES (
      p_cache_key, 'fixed', p_object_key, p_sha256, p_size_bytes,
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
    p_cache_key, p_object_key, p_sha256, p_size_bytes,
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

GRANT EXECUTE ON FUNCTION commit_fixed_cache TO service_role;
