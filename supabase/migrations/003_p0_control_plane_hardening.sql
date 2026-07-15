-- P0 control plane hardening (Issue #93).
-- Apply after 002_phase4_control_plane.sql.
--
-- Scope: public control-plane tables + commit_fixed_cache / commit_jpx_url_cache.
-- SupabaseRestAdapter grant map (service_role only):
--   runs: upsert_run, get_run, update_run, smoke cleanup DELETE
--   artifact_index: insert_artifact_index_pending, commit_artifact_index, mark_artifact_index_orphan, list_orphan_rows, delete_row
--   cache_index: insert_cache_index_pending_fixed, upsert_cache_index_pending_patched, commit_cache_index_patched, get_cache_index_patched, get_patched_cache_row, list_patched_cache_rows, mark_cache_index_orphan, list_orphan_rows, delete_row
--   cache_pointers: get_cache_pointer, DELETE (smoke/orphan-sweep), RPC upsert
--   monthly_snapshots: insert_monthly_snapshot_pending, commit_monthly_snapshot, mark_monthly_snapshot_orphan, list_committed_monthly_tags, list_orphan_rows, delete_row
--   publish_status: insert_publish_status_pending, commit_publish_status, mark_publish_status_orphan, get_publish_status, list_orphan_rows, delete_row
--   RPC: commit_fixed_cache, commit_jpx_url_cache
--
-- RPC signatures (fixed):
--   commit_fixed_cache(text, text, text, bigint, text, bigint, uuid)
--   commit_jpx_url_cache(text, text, bigint, text, bigint, uuid)

BEGIN;

-- 1) Enable RLS (no policies for anon/authenticated in P0).
ALTER TABLE public.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.artifact_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cache_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cache_pointers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthly_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.publish_status ENABLE ROW LEVEL SECURITY;

-- 2) Revoke non-privileged table ACL on existing objects.
REVOKE ALL ON TABLE public.runs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.artifact_index FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.cache_index FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.cache_pointers FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.monthly_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.publish_status FROM PUBLIC, anon, authenticated;

-- 3) Grant service_role table ACL required by GHA / smoke / orphan sweep.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.runs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.artifact_index TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.cache_index TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.cache_pointers TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.monthly_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.publish_status TO service_role;

-- 4) RPC EXECUTE: full signatures only.
REVOKE ALL ON FUNCTION public.commit_fixed_cache(
  text, text, text, bigint, text, bigint, uuid
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.commit_jpx_url_cache(
  text, text, bigint, text, bigint, uuid
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.commit_fixed_cache(
  text, text, text, bigint, text, bigint, uuid
) TO service_role;
GRANT EXECUTE ON FUNCTION public.commit_jpx_url_cache(
  text, text, bigint, text, bigint, uuid
) TO service_role;

-- Note: supabase_admin default privileges require separate owner-context apply; control-plane tables are postgres-owned.
-- 5) Default privileges — owners measured in baseline: postgres, supabase_admin.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO service_role;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO service_role;

-- 6) Post-apply catalog self-check (fail-fast rollback).
DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'runs', 'artifact_index', 'cache_index', 'cache_pointers',
    'monthly_snapshots', 'publish_status'
  ];
  r record;
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = t AND c.relrowsecurity
    ) THEN
      RAISE EXCEPTION 'P0 check failed: RLS not enabled on public.%', t;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = ANY (tables)
  ) THEN
    RAISE EXCEPTION 'P0 check failed: unexpected RLS policies on control-plane tables';
  END IF;

  FOR r IN
    SELECT grantee, table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND table_name = ANY (tables)
      AND grantee IN ('anon', 'authenticated', 'PUBLIC')
  LOOP
    RAISE EXCEPTION 'P0 check failed: residual grant % on %.% (%)',
      r.grantee, 'public', r.table_name, r.privilege_type;
  END LOOP;

  FOR r IN
    SELECT grantee, routine_name
    FROM information_schema.routine_privileges
    WHERE specific_schema = 'public'
      AND routine_name IN ('commit_fixed_cache', 'commit_jpx_url_cache')
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
      AND privilege_type = 'EXECUTE'
  LOOP
    RAISE EXCEPTION 'P0 check failed: residual RPC EXECUTE for % on %',
      r.grantee, r.routine_name;
  END LOOP;

  IF NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'P0 check failed: service_role must have rolbypassrls=true';
  END IF;

  FOREACH t IN ARRAY tables LOOP
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'SELECT') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing SELECT on %', t;
    END IF;
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'INSERT') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing INSERT on %', t;
    END IF;
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'UPDATE') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing UPDATE on %', t;
    END IF;
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'DELETE') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing DELETE on %', t;
    END IF;
  END LOOP;

  IF NOT has_function_privilege(
    'service_role',
    'public.commit_fixed_cache(text, text, text, bigint, text, bigint, uuid)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'P0 check failed: service_role missing EXECUTE on commit_fixed_cache';
  END IF;

  IF NOT has_function_privilege(
    'service_role',
    'public.commit_jpx_url_cache(text, text, bigint, text, bigint, uuid)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'P0 check failed: service_role missing EXECUTE on commit_jpx_url_cache';
  END IF;

  FOR r IN
    SELECT defaclrole::regrole::text AS owner, defaclobjtype, defaclacl::text AS acl
    FROM pg_default_acl
    WHERE defaclnamespace = 'public'::regnamespace
      AND defaclrole::regrole::text = 'postgres'
  LOOP
    IF r.acl ~ '(anon=|authenticated=|=anon/|=authenticated/)' THEN
      RAISE EXCEPTION 'P0 check failed: default ACL for % type % still grants anon/authenticated: %',
        r.owner, r.defaclobjtype, r.acl;
    END IF;
  END LOOP;
END $$;

COMMIT;
