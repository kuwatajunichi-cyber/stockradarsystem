-- Track C first-live entitlements + preferences (P0 inherit).
-- Git 026 after origin/main claimed 020. Production applied as
-- schema_migrations name 021_entitlements_preferences (version 20261002154055).
-- Do not re-apply. RLS ON, REVOKE PUBLIC/anon/authenticated, zero user policies, service_role only.
-- First-live roles are operator / internal_beta only. No user RLS. No webhook.

BEGIN;

CREATE TABLE IF NOT EXISTS public.entitlements (
  user_id UUID PRIMARY KEY REFERENCES auth.users (id),
  email TEXT NOT NULL,
  role TEXT NOT NULL
    CHECK (role IN ('operator', 'internal_beta')),
  status TEXT NOT NULL
    CHECK (status IN ('proven', 'revoked')),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  proven_at_utc TIMESTAMPTZ,
  revoked_at_utc TIMESTAMPTZ,
  CONSTRAINT entitlements_email_unique UNIQUE (email),
  CONSTRAINT entitlements_status_shape CHECK (
    (status = 'proven' AND proven_at_utc IS NOT NULL AND revoked_at_utc IS NULL)
    OR (status = 'revoked' AND revoked_at_utc IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS public.user_preferences (
  user_id UUID PRIMARY KEY REFERENCES auth.users (id),
  schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
  bag JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT user_preferences_bag_object CHECK (jsonb_typeof(bag) = 'object'),
  CONSTRAINT user_preferences_bag_size CHECK (octet_length(bag::text) <= 65536)
);

ALTER TABLE public.entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.entitlements FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.user_preferences FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.entitlements TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.user_preferences TO service_role;

DO $$
DECLARE
  r record;
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['entitlements', 'user_preferences']
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = t AND c.relrowsecurity
    ) THEN
      RAISE EXCEPTION 'P0 check failed: RLS not enabled on public.%', t;
    END IF;

    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = t
    ) THEN
      RAISE EXCEPTION 'P0 check failed: unexpected RLS policies on %', t;
    END IF;

    FOR r IN
      SELECT grantee, privilege_type
      FROM information_schema.role_table_grants
      WHERE table_schema = 'public'
        AND table_name = t
        AND grantee IN ('anon', 'authenticated', 'PUBLIC')
    LOOP
      RAISE EXCEPTION 'P0 check failed: residual grant % on % (%)',
        r.grantee, t, r.privilege_type;
    END LOOP;

    IF NOT has_table_privilege('service_role', format('public.%I', t), 'SELECT') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing SELECT on %', t;
    END IF;
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'INSERT') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing INSERT on %', t;
    END IF;
    IF NOT has_table_privilege('service_role', format('public.%I', t), 'UPDATE') THEN
      RAISE EXCEPTION 'P0 check failed: service_role missing UPDATE on %', t;
    END IF;
  END LOOP;

  IF NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'P0 check failed: service_role must have rolbypassrls=true';
  END IF;
END $$;

COMMIT;
