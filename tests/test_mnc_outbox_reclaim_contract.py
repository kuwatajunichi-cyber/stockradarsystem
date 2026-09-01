"""Contract: ADR-005 migration 014 outbox reclaim / heartbeat / finish / fail."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_MIG = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
_M014 = _MIG / "014_adr005_outbox_reclaim.sql"
_M015 = _MIG / "015_adr005_claim_outbox_by_request.sql"


def test_migration_014_outbox_reclaim_contract() -> None:
    raw = _M014.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    assert "CREATE OR REPLACE FUNCTION public.reconcile_mnc_outbox" in text
    assert "PERFORM public.reconcile_mnc_outbox()" in text
    assert "CREATE OR REPLACE FUNCTION public.claim_mnc_outbox" in text
    assert "CREATE OR REPLACE FUNCTION public.heartbeat_mnc_outbox" in text
    assert "CREATE OR REPLACE FUNCTION public.mark_mnc_outbox_dispatched" in text
    assert "CREATE OR REPLACE FUNCTION public.fail_mnc_outbox" in text
    assert "CREATE OR REPLACE FUNCTION public.finish_mnc_outbox_chunk" in text
    assert "fencing_mismatch" in text
    assert "GRANT EXECUTE ON FUNCTION public.heartbeat_mnc_outbox" in text
    assert "GRANT EXECUTE ON FUNCTION public.finish_mnc_outbox_chunk" in text
    assert "GRANT EXECUTE ON FUNCTION public.fail_mnc_outbox" in text


def test_migration_015_claim_outbox_by_request_contract() -> None:
    raw = _M015.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    assert "p_request_id TEXT DEFAULT NULL" in text
    assert "DROP FUNCTION IF EXISTS public.claim_mnc_outbox(text, int, int)" in text
    assert "o.request_id::text = trim(p_request_id)" in text
    assert "GRANT EXECUTE ON FUNCTION public.claim_mnc_outbox(text, int, int, text)" in text


def test_migration_016_fail_outbox_rejects_done_contract() -> None:
    path = _MIG / "016_adr005_fail_outbox_reject_done.sql"
    raw = path.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    assert "CREATE OR REPLACE FUNCTION public.fail_mnc_outbox" in text
    assert "v_row.status = 'done'" in text
    assert "bad_status" in text
