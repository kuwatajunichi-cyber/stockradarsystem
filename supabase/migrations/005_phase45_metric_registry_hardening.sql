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
GRANT SELECT, INSERT ON TABLE public.derived_object_index TO service_role;
GRANT SELECT ON TABLE public.latest_derived_observations TO service_role;

CREATE OR REPLACE FUNCTION public.enforce_metric_set_versions_insert_draft()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.lifecycle_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'metric_set_versions insert must be draft, got %', NEW.lifecycle_status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER metric_set_versions_insert_draft_only
  BEFORE INSERT ON public.metric_set_versions
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_metric_set_versions_insert_draft();

CREATE OR REPLACE FUNCTION public.enforce_derived_object_index_insert_pending()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM 'pending' THEN
    RAISE EXCEPTION 'derived_object_index insert must be pending, got %', NEW.status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER derived_object_index_insert_pending_only
  BEFORE INSERT ON public.derived_object_index
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_derived_object_index_insert_pending();

CREATE OR REPLACE FUNCTION public.enforce_metric_set_members_insert_draft_set()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  v_status TEXT;
BEGIN
  SELECT lifecycle_status INTO v_status
  FROM metric_set_versions
  WHERE id = NEW.metric_set_version_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'metric_set_members insert: unknown metric_set_version_id %', NEW.metric_set_version_id;
  END IF;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'metric_set_members insert requires draft set, got lifecycle %', v_status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER metric_set_members_insert_draft_set_only
  BEFORE INSERT ON public.metric_set_members
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_metric_set_members_insert_draft_set();

REVOKE ALL ON FUNCTION public.enforce_metric_set_versions_insert_draft() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.enforce_derived_object_index_insert_pending() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.enforce_metric_set_members_insert_draft_set() FROM PUBLIC, anon, authenticated;

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

  IF has_table_privilege('service_role', 'public.derived_object_index', 'UPDATE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not UPDATE public.derived_object_index';
  END IF;
  IF has_table_privilege('service_role', 'public.derived_object_index', 'DELETE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not DELETE public.derived_object_index';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.derived_object_index', 'INSERT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing INSERT on derived_object_index';
  END IF;

  IF has_table_privilege('service_role', 'public.latest_derived_observations', 'INSERT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not INSERT public.latest_derived_observations';
  END IF;
  IF has_table_privilege('service_role', 'public.latest_derived_observations', 'UPDATE') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role must not UPDATE public.latest_derived_observations';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.latest_derived_observations', 'SELECT') THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing SELECT on latest_derived_observations';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'metric_set_versions_insert_draft_only'
      AND tgrelid = 'public.metric_set_versions'::regclass
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: metric_set_versions_insert_draft_only trigger missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'derived_object_index_insert_pending_only'
      AND tgrelid = 'public.derived_object_index'::regclass
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: derived_object_index_insert_pending_only trigger missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'metric_set_members_insert_draft_set_only'
      AND tgrelid = 'public.metric_set_members'::regclass
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: metric_set_members_insert_draft_set_only trigger missing';
  END IF;

  IF NOT has_function_privilege(
    'service_role',
    'public.commit_derived_object(uuid, text, bigint, text)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing EXECUTE on commit_derived_object';
  END IF;

  IF NOT has_function_privilege(
    'service_role',
    'public.transition_metric_set(uuid, text, text)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Phase 4.5 check failed: service_role missing EXECUTE on transition_metric_set';
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
