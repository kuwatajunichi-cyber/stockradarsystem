-- Phase 4.5: commit_derived_generation statement_timeout (Issue #93 AC-LIVE).
-- Batch RPCs in 008 use 60s because they are chunked. Commit is a single
-- transaction that supersedes committed series coordinates; wall time grows
-- with derived_object_index size. PostgREST/session timeout otherwise returns
-- HTTP 500 (observed: canceling statement due to statement timeout).
-- Client adapter COMMIT_RPC_TIMEOUT_S is 180s; keep the function at the same bound.

BEGIN;

ALTER FUNCTION public.commit_derived_generation(uuid, text, text)
  SET statement_timeout = '180s';

COMMIT;
