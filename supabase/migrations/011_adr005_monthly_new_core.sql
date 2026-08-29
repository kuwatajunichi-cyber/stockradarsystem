-- ADR-005 P1: Monthly new-Core control plane and series-only generation CAS.
-- Apply after 010_phase45_commit_statement_timeout.sql.

BEGIN;

-- Existing fixed-cache RPCs intentionally omit version.  The default keeps
-- commit_fixed_cache and commit_jpx_url_cache backward compatible.
ALTER TABLE public.cache_pointers
  ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1
  CHECK (version > 0);

CREATE OR REPLACE FUNCTION public.commit_cache_pointer_cas(
  p_cache_key TEXT,
  p_expected_version BIGINT,
  p_object_key TEXT,
  p_sha256 TEXT,
  p_size_bytes BIGINT,
  p_writer_workflow TEXT,
  p_source_github_run_id BIGINT
) RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_current_version BIGINT;
  v_new_version BIGINT;
BEGIN
  IF p_cache_key IS NULL OR trim(p_cache_key) = ''
     OR p_object_key IS NULL OR trim(p_object_key) = ''
     OR p_sha256 !~ '^[a-f0-9]{64}$'
     OR p_size_bytes IS NULL OR p_size_bytes <= 0 THEN
    RAISE EXCEPTION 'commit_cache_pointer_cas: invalid pointer payload';
  END IF;

  SELECT version INTO v_current_version
  FROM public.cache_pointers
  WHERE cache_key = p_cache_key
  FOR UPDATE;

  IF NOT FOUND THEN
    IF p_expected_version <> 0 THEN
      RAISE EXCEPTION
        'cache_pointer_cas_conflict: expected % current 0', p_expected_version;
    END IF;
    INSERT INTO public.cache_pointers (
      cache_key, object_key, sha256, size_bytes, writer_workflow,
      source_github_run_id, committed_at_utc, version
    ) VALUES (
      p_cache_key, p_object_key, p_sha256, p_size_bytes, p_writer_workflow,
      p_source_github_run_id, now(), 1
    )
    RETURNING version INTO v_new_version;
    RETURN v_new_version;
  END IF;

  IF v_current_version <> p_expected_version THEN
    RAISE EXCEPTION
      'cache_pointer_cas_conflict: expected % current %',
      p_expected_version, v_current_version;
  END IF;

  UPDATE public.cache_pointers
  SET object_key = p_object_key,
      sha256 = p_sha256,
      size_bytes = p_size_bytes,
      writer_workflow = p_writer_workflow,
      source_github_run_id = p_source_github_run_id,
      committed_at_utc = now(),
      version = version + 1
  WHERE cache_key = p_cache_key
  RETURNING version INTO v_new_version;
  RETURN v_new_version;
END;
$$;

CREATE TABLE IF NOT EXISTS public.adr005_runtime_config (
  config_key TEXT PRIMARY KEY DEFAULT 'monthly_new_core'
    CHECK (config_key = 'monthly_new_core'),
  feature_start_release_month TEXT
    CHECK (
      feature_start_release_month IS NULL
      OR feature_start_release_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
    ),
  bootstrap_complete BOOLEAN NOT NULL DEFAULT false,
  series_seed_enabled BOOLEAN NOT NULL DEFAULT false,
  version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by TEXT
);

INSERT INTO public.adr005_runtime_config (config_key)
VALUES ('monthly_new_core')
ON CONFLICT (config_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.monthly_new_core_backfill_requests (
  id TEXT PRIMARY KEY CHECK (id ~ '^mnc-v1-[a-f0-9]{64}$'),
  monthly_snapshot_id UUID NOT NULL REFERENCES public.monthly_snapshots(id),
  release_month TEXT NOT NULL
    CHECK (release_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  previous_monthly_tag TEXT,
  current_core_logical_digest TEXT NOT NULL
    CHECK (current_core_logical_digest ~ '^[a-f0-9]{64}$'),
  metric_set_version_id UUID NOT NULL REFERENCES public.metric_set_versions(id),
  added_codes JSONB NOT NULL CHECK (jsonb_typeof(added_codes) = 'array'),
  added_codes_digest TEXT NOT NULL CHECK (added_codes_digest ~ '^[a-f0-9]{64}$'),
  partition_index INT NOT NULL DEFAULT 0 CHECK (partition_index >= 0),
  partition_count INT NOT NULL DEFAULT 1 CHECK (partition_count > 0),
  partition_codes_digest TEXT NOT NULL
    CHECK (partition_codes_digest ~ '^[a-f0-9]{64}$'),
  expected_trade_dates JSONB NOT NULL
    CHECK (jsonb_typeof(expected_trade_dates) = 'array'),
  expected_trade_dates_digest TEXT NOT NULL
    CHECK (expected_trade_dates_digest ~ '^[a-f0-9]{64}$'),
  coverage_start DATE,
  coverage_end DATE,
  required_input_start DATE,
  calendar_version TEXT NOT NULL,
  listing_source_policy TEXT NOT NULL DEFAULT 'first_valid_bar'
    CHECK (listing_source_policy = 'first_valid_bar'),
  status TEXT NOT NULL CHECK (
    status IN (
      'dispatch_pending', 'dispatched', 'dispatch_failed',
      'ohlcv_running', 'ohlcv_ready', 'series_running',
      'failed_retryable', 'completed', 'noop', 'blocked',
      'grandfather', 'paused', 'superseded'
    )
  ),
  reason_code TEXT,
  last_committed_trade_date DATE,
  candidate_digest TEXT CHECK (
    candidate_digest IS NULL OR candidate_digest ~ '^[a-f0-9]{64}$'
  ),
  expected_digest TEXT CHECK (
    expected_digest IS NULL OR expected_digest ~ '^[a-f0-9]{64}$'
  ),
  exclusion_digest TEXT CHECK (
    exclusion_digest IS NULL OR exclusion_digest ~ '^[a-f0-9]{64}$'
  ),
  resolved_digest TEXT CHECK (
    resolved_digest IS NULL OR resolved_digest ~ '^[a-f0-9]{64}$'
  ),
  conflict_count INT NOT NULL DEFAULT 0 CHECK (conflict_count >= 0),
  uncommitted_count INT NOT NULL DEFAULT 0 CHECK (uncommitted_count >= 0),
  manifest_object_key TEXT,
  manifest_version BIGINT NOT NULL DEFAULT 1 CHECK (manifest_version > 0),
  version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
  successor_request_id TEXT REFERENCES public.monthly_new_core_backfill_requests(id),
  heartbeat_at TIMESTAMPTZ,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at_utc TIMESTAMPTZ,
  CONSTRAINT monthly_new_core_partition_bounds CHECK (
    partition_index < partition_count
  ),
  CONSTRAINT monthly_new_core_coverage_bounds CHECK (
    (coverage_start IS NULL AND coverage_end IS NULL)
    OR (
      coverage_start IS NOT NULL
      AND coverage_end IS NOT NULL
      AND coverage_start <= coverage_end
      AND required_input_start IS NOT NULL
      AND required_input_start <= coverage_start
    )
  ),
  UNIQUE (
    monthly_snapshot_id, metric_set_version_id,
    current_core_logical_digest, partition_index
  )
);

CREATE INDEX IF NOT EXISTS monthly_new_core_requests_release_month
  ON public.monthly_new_core_backfill_requests (release_month, partition_index);
CREATE INDEX IF NOT EXISTS monthly_new_core_requests_status
  ON public.monthly_new_core_backfill_requests (status, updated_at_utc);

CREATE TABLE IF NOT EXISTS public.request_release_links (
  monthly_snapshot_id UUID NOT NULL REFERENCES public.monthly_snapshots(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL
    REFERENCES public.monthly_new_core_backfill_requests(id) ON DELETE CASCADE,
  link_role TEXT NOT NULL
    CHECK (link_role IN ('canonical_winner', 'noncanonical_loser')),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (monthly_snapshot_id, request_id, link_role)
);

CREATE UNIQUE INDEX IF NOT EXISTS request_release_links_one_loser
  ON public.request_release_links (monthly_snapshot_id)
  WHERE link_role = 'noncanonical_loser';

CREATE TABLE IF NOT EXISTS public.monthly_new_core_backfill_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id TEXT NOT NULL
    REFERENCES public.monthly_new_core_backfill_requests(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  reason_code TEXT,
  details JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (jsonb_typeof(details) = 'object'),
  actor TEXT NOT NULL,
  fencing_token BIGINT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS monthly_new_core_events_request_created
  ON public.monthly_new_core_backfill_events (request_id, created_at_utc);

CREATE TABLE IF NOT EXISTS public.monthly_new_core_backfill_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id TEXT NOT NULL
    REFERENCES public.monthly_new_core_backfill_requests(id) ON DELETE CASCADE,
  chunk_seq INT NOT NULL CHECK (chunk_seq >= 0),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'claimed', 'dispatched', 'done', 'failed')),
  attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  attempt_budget INT NOT NULL DEFAULT 5 CHECK (attempt_budget > 0),
  fencing_token BIGINT NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  claimed_by TEXT,
  github_run_id BIGINT,
  heartbeat_at TIMESTAMPTZ,
  visibility_timeout_at TIMESTAMPTZ,
  next_retry_at TIMESTAMPTZ,
  last_error TEXT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  done_at_utc TIMESTAMPTZ,
  UNIQUE (request_id, chunk_seq)
);

CREATE UNIQUE INDEX IF NOT EXISTS monthly_new_core_one_nonterminal_outbox
  ON public.monthly_new_core_backfill_outbox (request_id)
  WHERE status IN ('pending', 'claimed', 'dispatched', 'failed');

CREATE INDEX IF NOT EXISTS monthly_new_core_outbox_claim
  ON public.monthly_new_core_backfill_outbox (status, next_retry_at, created_at_utc);

CREATE TABLE IF NOT EXISTS public.series_write_leases (
  metric_set_version_id UUID NOT NULL REFERENCES public.metric_set_versions(id),
  instrument_code TEXT NOT NULL,
  series_year INT NOT NULL CHECK (series_year BETWEEN 1900 AND 2100),
  owner_generation_id UUID REFERENCES public.derived_generation_runs(id),
  owner_kind TEXT NOT NULL CHECK (
    owner_kind IN ('daily_normal', 'reconcile', 'series_seed', 'series_repair')
  ),
  fencing_token BIGINT NOT NULL DEFAULT 1 CHECK (fencing_token > 0),
  heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (metric_set_version_id, instrument_code, series_year)
);

CREATE TABLE IF NOT EXISTS public.adr005_cache_key_leases (
  cache_key TEXT PRIMARY KEY,
  owner_request_id TEXT
    REFERENCES public.monthly_new_core_backfill_requests(id) ON DELETE CASCADE,
  fencing_token BIGINT NOT NULL DEFAULT 1 CHECK (fencing_token > 0),
  heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS public.monthly_new_core_series_repairs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id TEXT NOT NULL
    REFERENCES public.monthly_new_core_backfill_requests(id) ON DELETE CASCADE,
  trade_date DATE NOT NULL,
  instrument_code TEXT NOT NULL,
  series_year INT NOT NULL CHECK (series_year BETWEEN 1900 AND 2100),
  expected_prior_logical_digest TEXT NOT NULL
    CHECK (expected_prior_logical_digest ~ '^[a-f0-9]{64}$'),
  reason TEXT NOT NULL CHECK (trim(reason) <> ''),
  approver_github_login TEXT NOT NULL CHECK (trim(approver_github_login) <> ''),
  worker_github_actor TEXT NOT NULL CHECK (trim(worker_github_actor) <> ''),
  status TEXT NOT NULL DEFAULT 'approved'
    CHECK (status IN ('approved', 'committed', 'rejected', 'superseded')),
  generation_id UUID REFERENCES public.derived_generation_runs(id),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  committed_at_utc TIMESTAMPTZ,
  CONSTRAINT monthly_new_core_repair_no_self_approval CHECK (
    lower(approver_github_login) <> lower(worker_github_actor)
  ),
  UNIQUE (request_id, trade_date, instrument_code, series_year)
);

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
      updated_at_utc = now()
  FROM candidates c
  WHERE o.id = c.id
  RETURNING o.*;
END;
$$;

-- Expand generation and object contracts.
ALTER TABLE public.derived_generation_runs
  DROP CONSTRAINT IF EXISTS derived_generation_runs_mode_check;
ALTER TABLE public.derived_generation_runs
  ADD CONSTRAINT derived_generation_runs_mode_check CHECK (
    mode IN (
      'normal', 'replay', 'backfill', 'reconcile',
      'series_seed', 'series_repair'
    )
  );

ALTER TABLE public.derived_generation_runs
  DROP CONSTRAINT IF EXISTS derived_generation_runs_artifact_profile_check;
ALTER TABLE public.derived_generation_runs
  ADD CONSTRAINT derived_generation_runs_artifact_profile_check CHECK (
    artifact_profile IN (
      'snapshot_only', 'snapshot_series', 'snapshot_series_latest', 'series_only'
    )
  );

ALTER TABLE public.derived_generation_runs
  ADD COLUMN IF NOT EXISTS request_id TEXT
    REFERENCES public.monthly_new_core_backfill_requests(id),
  ADD COLUMN IF NOT EXISTS series_cas_payload JSONB;

CREATE TABLE IF NOT EXISTS public.derived_generation_series_cas (
  generation_id UUID NOT NULL
    REFERENCES public.derived_generation_runs(id) ON DELETE CASCADE,
  metric_set_version_id UUID NOT NULL REFERENCES public.metric_set_versions(id),
  instrument_code TEXT NOT NULL,
  series_year INT NOT NULL CHECK (series_year BETWEEN 1900 AND 2100),
  expected_prior_logical_digest TEXT CHECK (
    expected_prior_logical_digest IS NULL
    OR expected_prior_logical_digest ~ '^[a-f0-9]{64}$'
  ),
  prior_absent BOOLEAN NOT NULL,
  PRIMARY KEY (generation_id, instrument_code, series_year),
  CONSTRAINT derived_generation_series_cas_expected_state CHECK (
    (prior_absent AND expected_prior_logical_digest IS NULL)
    OR (
      NOT prior_absent
      AND expected_prior_logical_digest IS NOT NULL
    )
  )
);

ALTER TABLE public.derived_object_index
  ADD COLUMN IF NOT EXISTS request_id TEXT
    REFERENCES public.monthly_new_core_backfill_requests(id);

CREATE OR REPLACE FUNCTION public.set_derived_object_request_id()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.request_id IS NULL AND NEW.generation_id IS NOT NULL THEN
    SELECT g.request_id INTO NEW.request_id
    FROM public.derived_generation_runs g
    WHERE g.id = NEW.generation_id;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS derived_object_request_id_from_generation
  ON public.derived_object_index;
CREATE TRIGGER derived_object_request_id_from_generation
BEFORE INSERT ON public.derived_object_index
FOR EACH ROW
EXECUTE FUNCTION public.set_derived_object_request_id();

ALTER TABLE public.derived_object_index
  DROP CONSTRAINT IF EXISTS derived_object_index_object_kind_check;
ALTER TABLE public.derived_object_index
  ADD CONSTRAINT derived_object_index_object_kind_check CHECK (
    object_kind IN (
      'snapshot', 'series', 'snapshot_manifest', 'series_manifest',
      'series_seed_delta', 'series_repair_delta'
    )
  );

ALTER TABLE public.derived_object_index
  DROP CONSTRAINT IF EXISTS derived_object_index_status_check;
ALTER TABLE public.derived_object_index
  ADD CONSTRAINT derived_object_index_status_check CHECK (
    status IN ('pending', 'committed', 'orphan', 'superseded')
  );

ALTER TABLE public.derived_object_index
  DROP CONSTRAINT IF EXISTS derived_object_shape;
ALTER TABLE public.derived_object_index
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
    OR (
      object_kind IN ('series_seed_delta', 'series_repair_delta')
      AND trade_date IS NOT NULL
      AND instrument_code IS NULL
      AND series_year IS NULL
      AND request_id IS NOT NULL
    )
  );

ALTER TABLE public.derived_object_index
  DROP CONSTRAINT IF EXISTS derived_object_committed_ts;
ALTER TABLE public.derived_object_index
  ADD CONSTRAINT derived_object_committed_ts CHECK (
    (
      status IN ('committed', 'superseded')
      AND committed_at_utc IS NOT NULL
    )
    OR status IN ('pending', 'orphan')
  );

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_delta_coordinate
  ON public.derived_object_index (request_id, trade_date, object_kind)
  WHERE (
    object_kind IN ('series_seed_delta', 'series_repair_delta')
    AND status = 'committed'
  );

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_series_coordinate
  ON public.derived_object_index (
    metric_set_version_id, instrument_code, series_year
  )
  WHERE object_kind = 'series' AND status = 'committed';

-- Replace the exact 006 overload.  New arguments have defaults so existing
-- Daily named-RPC payloads keep resolving without extra keys.
DROP FUNCTION IF EXISTS public.begin_derived_generation(
  uuid, date, text, text, text, text, bigint, int, text, uuid,
  text, text, int, text, text
);

CREATE FUNCTION public.begin_derived_generation(
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
  p_expected_latest_set_digest TEXT,
  p_series_coordinates JSONB DEFAULT NULL,
  p_expected_prior_logical_digest JSONB DEFAULT NULL,
  p_prior_absent JSONB DEFAULT NULL,
  p_request_id TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_existing public.derived_generation_runs%ROWTYPE;
  v_id UUID;
  v_item RECORD;
  v_code TEXT;
  v_year INT;
  v_expected TEXT;
  v_absent BOOLEAN;
  v_cas_payload JSONB;
BEGIN
  IF p_artifact_profile = 'series_only' THEN
    IF p_mode NOT IN ('series_seed', 'series_repair') THEN
      RAISE EXCEPTION
        'begin_derived_generation: series_only requires series_seed or series_repair';
    END IF;
    IF p_series_coordinates IS NULL
       OR p_expected_prior_logical_digest IS NULL
       OR p_prior_absent IS NULL
       OR jsonb_typeof(p_series_coordinates) <> 'array'
       OR jsonb_typeof(p_expected_prior_logical_digest) <> 'array'
       OR jsonb_typeof(p_prior_absent) <> 'array'
       OR jsonb_array_length(p_series_coordinates) = 0
       OR jsonb_array_length(p_series_coordinates)
          <> jsonb_array_length(p_expected_prior_logical_digest)
       OR jsonb_array_length(p_series_coordinates)
          <> jsonb_array_length(p_prior_absent) THEN
      RAISE EXCEPTION
        'begin_derived_generation: invalid series CAS coordinate arrays';
    END IF;
    IF p_request_id IS NULL OR trim(p_request_id) = '' THEN
      RAISE EXCEPTION 'begin_derived_generation: series_only requires request_id';
    END IF;

    SELECT jsonb_agg(
      jsonb_build_object(
        'instrument_code', trim(c.value->>'instrument_code'),
        'series_year', (c.value->>'series_year')::INT,
        'expected_prior_logical_digest',
          CASE WHEN jsonb_typeof(e.value) = 'null' THEN NULL ELSE e.value #>> '{}' END,
        'prior_absent', (a.value #>> '{}')::BOOLEAN
      )
      ORDER BY trim(c.value->>'instrument_code'), (c.value->>'series_year')::INT
    )
    INTO v_cas_payload
    FROM jsonb_array_elements(p_series_coordinates) WITH ORDINALITY c(value, n)
    JOIN jsonb_array_elements(p_expected_prior_logical_digest)
      WITH ORDINALITY e(value, n) USING (n)
    JOIN jsonb_array_elements(p_prior_absent)
      WITH ORDINALITY a(value, n) USING (n);

    FOR v_item IN
      SELECT value
      FROM jsonb_array_elements(v_cas_payload)
    LOOP
      v_code := trim(v_item.value->>'instrument_code');
      v_year := (v_item.value->>'series_year')::INT;
      v_expected := NULLIF(v_item.value->>'expected_prior_logical_digest', '');
      v_absent := (v_item.value->>'prior_absent')::BOOLEAN;
      IF v_code = '' OR v_year NOT BETWEEN 1900 AND 2100
         OR (v_absent AND v_expected IS NOT NULL)
         OR (
           NOT v_absent
           AND (v_expected IS NULL OR v_expected !~ '^[a-f0-9]{64}$')
         ) THEN
        RAISE EXCEPTION
          'begin_derived_generation: invalid series CAS coordinate';
      END IF;
    END LOOP;
  ELSE
    IF p_series_coordinates IS NOT NULL
       OR p_expected_prior_logical_digest IS NOT NULL
       OR p_prior_absent IS NOT NULL
       OR p_request_id IS NOT NULL THEN
      RAISE EXCEPTION
        'begin_derived_generation: series CAS arguments require series_only';
    END IF;
    v_cas_payload := NULL;
  END IF;

  SELECT * INTO v_existing
  FROM public.derived_generation_runs
  WHERE repository = p_repository
    AND workflow = p_workflow
    AND github_run_id = p_github_run_id
    AND metric_set_version_id = p_metric_set_version_id
    AND trade_date = p_trade_date
    AND mode = p_mode
  FOR UPDATE;

  IF FOUND THEN
    IF v_existing.status = 'failed' THEN
      RAISE EXCEPTION
        'derived generation failed; new source identity required (set_uuid=%)',
        p_metric_set_version_id;
    END IF;
    IF v_existing.artifact_profile IS DISTINCT FROM p_artifact_profile
       OR v_existing.expected_object_count IS DISTINCT FROM p_expected_object_count
       OR v_existing.expected_object_set_digest IS DISTINCT FROM p_expected_object_set_digest
       OR v_existing.expected_latest_set_digest IS DISTINCT FROM p_expected_latest_set_digest
       OR v_existing.declared_new_digest IS DISTINCT FROM p_declared_new_digest
       OR (
         p_expected_old_digest IS NOT NULL
         AND v_existing.expected_old_digest IS DISTINCT FROM p_expected_old_digest
       )
       OR v_existing.series_cas_payload IS DISTINCT FROM v_cas_payload
       OR v_existing.request_id IS DISTINCT FROM p_request_id THEN
      RAISE EXCEPTION
        'derived generation payload mismatch for source identity (set_uuid=%)',
        p_metric_set_version_id;
    END IF;
    IF v_existing.status = 'committed' THEN
      RETURN v_existing.id;
    END IF;
    UPDATE public.derived_generation_runs
    SET heartbeat_at = now(),
        updated_at_utc = now(),
        run_attempt = COALESCE(p_run_attempt, run_attempt)
    WHERE id = v_existing.id;
    RETURN v_existing.id;
  END IF;

  INSERT INTO public.derived_generation_runs (
    metric_set_version_id, trade_date, mode, artifact_profile,
    expected_old_digest, declared_new_digest,
    expected_object_count, expected_object_set_digest, expected_latest_set_digest,
    repository, workflow, github_run_id, run_attempt,
    writer_workflow, source_run_id, status, heartbeat_at,
    request_id, series_cas_payload
  ) VALUES (
    p_metric_set_version_id, p_trade_date, p_mode, p_artifact_profile,
    p_expected_old_digest, p_declared_new_digest,
    p_expected_object_count, p_expected_object_set_digest, p_expected_latest_set_digest,
    p_repository, p_workflow, p_github_run_id, COALESCE(p_run_attempt, 1),
    p_writer_workflow, p_source_run_id, 'pending', now(),
    p_request_id, v_cas_payload
  )
  RETURNING id INTO v_id;

  IF v_cas_payload IS NOT NULL THEN
    INSERT INTO public.derived_generation_series_cas (
      generation_id, metric_set_version_id, instrument_code, series_year,
      expected_prior_logical_digest, prior_absent
    )
    SELECT
      v_id,
      p_metric_set_version_id,
      trim(value->>'instrument_code'),
      (value->>'series_year')::INT,
      NULLIF(value->>'expected_prior_logical_digest', ''),
      (value->>'prior_absent')::BOOLEAN
    FROM jsonb_array_elements(v_cas_payload);
  END IF;

  RETURN v_id;
END;
$$;

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

-- Defense in depth: CREATE OR REPLACE resets function settings.
ALTER FUNCTION public.commit_derived_generation(uuid, text, text)
  SET statement_timeout = '180s';

REVOKE ALL ON FUNCTION public.commit_cache_pointer_cas(
  text, bigint, text, text, bigint, text, bigint
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_cache_pointer_cas(
  text, bigint, text, text, bigint, text, bigint
) TO service_role;

REVOKE ALL ON FUNCTION public.set_derived_object_request_id()
  FROM PUBLIC, anon, authenticated;

REVOKE ALL ON FUNCTION public.claim_mnc_outbox(text, int, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_mnc_outbox(text, int, int)
  TO service_role;

REVOKE ALL ON FUNCTION public.begin_derived_generation(
  uuid, date, text, text, text, text, bigint, int, text, uuid,
  text, text, int, text, text, jsonb, jsonb, jsonb, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.begin_derived_generation(
  uuid, date, text, text, text, text, bigint, int, text, uuid,
  text, text, int, text, text, jsonb, jsonb, jsonb, text
) TO service_role;

REVOKE ALL ON FUNCTION public.commit_derived_generation(uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text, text)
  TO service_role;

ALTER TABLE public.adr005_runtime_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthly_new_core_backfill_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_release_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthly_new_core_backfill_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthly_new_core_backfill_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.series_write_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adr005_cache_key_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthly_new_core_series_repairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.derived_generation_series_cas ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.adr005_runtime_config
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.monthly_new_core_backfill_requests
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.request_release_links
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.monthly_new_core_backfill_events
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.monthly_new_core_backfill_outbox
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.series_write_leases
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.adr005_cache_key_leases
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.monthly_new_core_series_repairs
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.derived_generation_series_cas
  FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE ON TABLE public.adr005_runtime_config
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.monthly_new_core_backfill_requests
  TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.request_release_links
  TO service_role;
GRANT SELECT, INSERT ON TABLE public.monthly_new_core_backfill_events
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.monthly_new_core_backfill_outbox
  TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.series_write_leases
  TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.adr005_cache_key_leases
  TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.monthly_new_core_series_repairs
  TO service_role;
GRANT SELECT, INSERT ON TABLE public.derived_generation_series_cas
  TO service_role;

COMMIT;
