-- Phase 4.5 metric registry hardening (Issue #93).
-- Apply after 004_phase45_metric_registry.sql.
--
-- RPC signatures (fixed):
--   commit_derived_object(uuid, text, bigint, text)
--   transition_metric_set(uuid, text, text)
--   activate_metric_set_cas(uuid, uuid, text, bigint)

BEGIN;

ALTER TABLE public.metric_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metric_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metric_set_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metric_set_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.active_metric_set ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.derived_object_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.latest_derived_observations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.metric_definitions FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.metric_versions FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.metric_set_versions FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.metric_set_members FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.active_metric_set FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.derived_object_index FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.latest_derived_observations FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT ON TABLE public.metric_definitions TO service_role;
GRANT SELECT, INSERT ON TABLE public.metric_versions TO service_role;
GRANT SELECT, INSERT ON TABLE public.metric_set_versions TO service_role;
GRANT SELECT, INSERT ON TABLE public.metric_set_members TO service_role;
GRANT SELECT ON TABLE public.active_metric_set TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.derived_object_index TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.latest_derived_observations TO service_role;

REVOKE ALL ON FUNCTION public.commit_derived_object(uuid, text, bigint, text)
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.transition_metric_set(uuid, text, text)
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.activate_metric_set_cas(uuid, uuid, text, bigint)
  FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.commit_derived_object(uuid, text, bigint, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.transition_metric_set(uuid, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.activate_metric_set_cas(uuid, uuid, text, bigint) TO service_role;

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'metric_definitions', 'metric_versions', 'metric_set_versions', 'metric_set_members',
    'active_metric_set', 'derived_object_index', 'latest_derived_observations'
  ];
  r record;
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = t AND c.relrowsecurity
    ) THEN
      RAISE EXCEPTION 'RLS not enabled on %', t;
    END IF;
  END LOOP;

  FOR r IN
    SELECT grantee, table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND table_name = ANY (tables)
      AND grantee IN ('anon', 'authenticated', 'PUBLIC')
  LOOP
    RAISE EXCEPTION 'Phase 4.5 check failed: residual grant % on public.% (%)',
      r.grantee, r.table_name, r.privilege_type;
  END LOOP;

  FOR r IN
    SELECT grantee, routine_name
    FROM information_schema.routine_privileges
    WHERE specific_schema = 'public'
      AND routine_name IN (
        'commit_derived_object', 'transition_metric_set', 'activate_metric_set_cas'
      )
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
      AND privilege_type = 'EXECUTE'
  LOOP
    RAISE EXCEPTION 'Phase 4.5 check failed: residual RPC EXECUTE for % on %',
      r.grantee, r.routine_name;
  END LOOP;

  FOREACH t IN ARRAY ARRAY[
    'metric_definitions', 'metric_versions', 'metric_set_versions', 'metric_set_members'
  ] LOOP
    IF has_table_privilege('service_role', format('public.%I', t), 'UPDATE') THEN
      RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not UPDATE public.%', t;
    END IF;
    IF has_table_privilege('service_role', format('public.%I', t), 'DELETE') THEN
      RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not DELETE public.%', t;
    END IF;
  END LOOP;

  IF has_table_privilege('service_role', 'public.active_metric_set', 'INSERT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not INSERT public.active_metric_set';
  END IF;
  IF has_table_privilege('service_role', 'public.active_metric_set', 'UPDATE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not UPDATE public.active_metric_set';
  END IF;
  IF has_table_privilege('service_role', 'public.active_metric_set', 'DELETE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not DELETE public.active_metric_set';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.active_metric_set', 'SELECT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing SELECT on active_metric_set';
  END IF;

  IF NOT has_table_privilege('service_role', 'public.metric_set_versions', 'SELECT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing SELECT on metric_set_versions';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.derived_object_index', 'DELETE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing DELETE on derived_object_index';
  END IF;

  IF NOT has_function_privilege(
    'service_role',
    'public.activate_metric_set_cas(uuid, uuid, text, bigint)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing EXECUTE on activate_metric_set_cas';
  END IF;
END $$;

COMMIT;
