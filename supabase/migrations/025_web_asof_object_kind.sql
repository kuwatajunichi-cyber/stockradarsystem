-- Track D derived-web-asof control plane (object_kind + benchmark).
-- Git 025: origin/main already owns 020_delete_orphan_derived_objects.sql.
-- Production applied this DDL as schema_migrations name 020_web_asof_object_kind
-- (version 20261002132947). Do not re-apply. P0 inherit: no new anon/authenticated grants.
-- Does not CAS metric_set. Does not mint.

BEGIN;

ALTER TABLE public.derived_object_index
  ADD COLUMN IF NOT EXISTS benchmark TEXT;

ALTER TABLE public.derived_object_index
  DROP CONSTRAINT IF EXISTS derived_object_index_object_kind_check;
ALTER TABLE public.derived_object_index
  ADD CONSTRAINT derived_object_index_object_kind_check CHECK (
    object_kind IN (
      'snapshot', 'series', 'snapshot_manifest', 'series_manifest',
      'series_seed_delta', 'series_repair_delta',
      'web_asof_bundle', 'web_asof_manifest'
    )
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
      AND benchmark IS NULL
    )
    OR (
      object_kind IN ('series', 'series_manifest')
      AND instrument_code IS NOT NULL
      AND series_year IS NOT NULL
      AND trade_date IS NULL
      AND benchmark IS NULL
    )
    OR (
      object_kind IN ('series_seed_delta', 'series_repair_delta')
      AND trade_date IS NOT NULL
      AND instrument_code IS NULL
      AND series_year IS NULL
      AND request_id IS NOT NULL
      AND benchmark IS NULL
    )
    OR (
      object_kind = 'web_asof_bundle'
      AND trade_date IS NOT NULL
      AND instrument_code IS NULL
      AND series_year IS NULL
      AND benchmark IN ('topix', 'nikkei')
    )
    OR (
      object_kind = 'web_asof_manifest'
      AND trade_date IS NOT NULL
      AND instrument_code IS NULL
      AND series_year IS NULL
      AND benchmark IS NULL
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS derived_object_index_committed_web_asof_bundle
  ON public.derived_object_index (metric_set_version_id, benchmark, trade_date)
  WHERE object_kind = 'web_asof_bundle' AND status = 'committed';

COMMIT;
