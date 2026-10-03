-- Track D web_asof artifact_profile (P0 inherit).
-- Git 027. Production applied as schema_migrations name 022_web_asof_artifact_profile
-- (version 20261003063413). Do not re-apply.
-- Does not CAS metric_set. Does not mint. Does not add user policies.
-- Commit orphan for web_asof is 028.

BEGIN;

ALTER TABLE public.derived_generation_runs
  DROP CONSTRAINT IF EXISTS derived_generation_runs_artifact_profile_check;
ALTER TABLE public.derived_generation_runs
  ADD CONSTRAINT derived_generation_runs_artifact_profile_check CHECK (
    artifact_profile IN (
      'snapshot_only', 'snapshot_series', 'snapshot_series_latest',
      'series_only', 'web_asof'
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_web_asof_manifest
  ON public.derived_object_index (metric_set_version_id, trade_date)
  WHERE object_kind = 'web_asof_manifest' AND status = 'committed';

COMMIT;
