-- Track B download_grants audit (signed URL capability).
-- P0 inherit: RLS ON, REVOKE anon/authenticated/PUBLIC, zero user policies, service_role only.
-- Do not store signed URL bodies or R2 secrets.

BEGIN;

CREATE TABLE IF NOT EXISTS public.download_grants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_id TEXT NOT NULL,
  object_key TEXT NOT NULL DEFAULT '',
  source_table TEXT,
  source_id TEXT,
  sha256 TEXT,
  actor_ref TEXT NOT NULL,
  operation TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL,
  expires_at_utc TIMESTAMPTZ,
  mint_result TEXT NOT NULL
    CHECK (mint_result IN ('issued', 'denied')),
  reason_code TEXT,
  CONSTRAINT download_grants_issued_has_expiry CHECK (
    (mint_result = 'issued' AND expires_at_utc IS NOT NULL AND reason_code IS NULL)
    OR (mint_result = 'denied' AND expires_at_utc IS NULL AND reason_code IS NOT NULL)
  ),
  CONSTRAINT download_grants_no_signed_url_column CHECK (true)
);

CREATE INDEX IF NOT EXISTS download_grants_request_id
  ON public.download_grants (request_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS download_grants_object_key
  ON public.download_grants (object_key, created_at_utc DESC);

ALTER TABLE public.download_grants ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.download_grants FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.download_grants TO service_role;

DO $$
DECLARE
  r record;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'download_grants' AND c.relrowsecurity
  ) THEN
    RAISE EXCEPTION 'P0 check failed: RLS not enabled on public.download_grants';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'download_grants'
  ) THEN
    RAISE EXCEPTION 'P0 check failed: unexpected RLS policies on download_grants';
  END IF;

  FOR r IN
    SELECT grantee, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND table_name = 'download_grants'
      AND grantee IN ('anon', 'authenticated', 'PUBLIC')
  LOOP
    RAISE EXCEPTION 'P0 check failed: residual grant % on download_grants (%)',
      r.grantee, r.privilege_type;
  END LOOP;

  IF NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'P0 check failed: service_role must have rolbypassrls=true';
  END IF;

  IF NOT has_table_privilege('service_role', 'public.download_grants', 'SELECT') THEN
    RAISE EXCEPTION 'P0 check failed: service_role missing SELECT on download_grants';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.download_grants', 'INSERT') THEN
    RAISE EXCEPTION 'P0 check failed: service_role missing INSERT on download_grants';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.download_grants', 'UPDATE') THEN
    RAISE EXCEPTION 'P0 check failed: service_role missing UPDATE on download_grants';
  END IF;
END $$;

COMMIT;
