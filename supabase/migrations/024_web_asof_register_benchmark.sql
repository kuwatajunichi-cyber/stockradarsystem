-- Track D: register_pending_derived_object includes benchmark (P0 inherit).
-- Does not CAS metric_set. Does not mint.

BEGIN;

DROP FUNCTION IF EXISTS public.register_pending_derived_object(
  uuid, text, text, text, text, text, date, text, integer
);

CREATE OR REPLACE FUNCTION public.register_pending_derived_object(
  p_generation_id UUID,
  p_object_kind TEXT,
  p_object_key TEXT,
  p_logical_digest TEXT,
  p_layer1_input_fingerprint TEXT,
  p_writer_workflow TEXT,
  p_trade_date DATE,
  p_instrument_code TEXT,
  p_series_year INT,
  p_benchmark TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_gen derived_generation_runs%ROWTYPE;
  v_row derived_object_index%ROWTYPE;
  v_id UUID;
  v_bench TEXT;
BEGIN
  v_bench := NULLIF(lower(trim(p_benchmark)), '');

  SELECT * INTO v_gen FROM derived_generation_runs WHERE id = p_generation_id FOR UPDATE;
  IF NOT FOUND OR v_gen.status <> 'pending' THEN
    RAISE EXCEPTION 'register_pending_derived_object: generation % not pending', p_generation_id;
  END IF;

  SELECT * INTO v_row
  FROM derived_object_index
  WHERE generation_id = p_generation_id
    AND object_kind = p_object_kind
    AND trade_date IS NOT DISTINCT FROM p_trade_date
    AND instrument_code IS NOT DISTINCT FROM p_instrument_code
    AND series_year IS NOT DISTINCT FROM p_series_year
    AND benchmark IS NOT DISTINCT FROM v_bench
  FOR UPDATE;

  IF FOUND THEN
    IF v_row.logical_digest = p_logical_digest THEN
      RETURN v_row.id;
    END IF;
    RAISE EXCEPTION 'register_pending_derived_object: coordinate conflict for generation %', p_generation_id;
  END IF;

  INSERT INTO derived_object_index (
    object_kind, metric_set_version_id, trade_date, instrument_code, series_year,
    benchmark, object_key, logical_digest, layer1_input_fingerprint, writer_workflow,
    generation_id, status
  ) VALUES (
    p_object_kind, v_gen.metric_set_version_id, p_trade_date, p_instrument_code, p_series_year,
    v_bench, p_object_key, p_logical_digest, p_layer1_input_fingerprint, p_writer_workflow,
    p_generation_id, 'pending'
  )
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION public.register_pending_derived_object(
  uuid, text, text, text, text, text, date, text, integer, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_pending_derived_object(
  uuid, text, text, text, text, text, date, text, integer, text
) TO service_role;

COMMIT;
