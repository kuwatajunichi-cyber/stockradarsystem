-- Batch-delete derived_object_index rows with status=orphan only.
-- Never deletes committed / superseded / pending.
-- Caller loops until the function returns 0. p_limit is capped at 20000.

BEGIN;

CREATE OR REPLACE FUNCTION public.delete_orphan_derived_objects(p_limit integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '120s'
AS $$
DECLARE
  n integer := 0;
  v_limit integer;
BEGIN
  IF p_limit IS NULL OR p_limit < 1 THEN
    RAISE EXCEPTION 'delete_orphan_derived_objects: p_limit must be >= 1';
  END IF;
  v_limit := LEAST(p_limit, 20000);
  DELETE FROM public.derived_object_index
  WHERE id IN (
    SELECT id
    FROM public.derived_object_index
    WHERE status = 'orphan'
    LIMIT v_limit
  );
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END;
$$;

REVOKE ALL ON FUNCTION public.delete_orphan_derived_objects(integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.delete_orphan_derived_objects(integer) TO service_role;

COMMIT;
