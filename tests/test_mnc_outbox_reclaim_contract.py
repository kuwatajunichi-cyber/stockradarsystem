"""Contract: ADR-005 migration 014 outbox reclaim / heartbeat / finish / fail."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_M014 = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "014_adr005_outbox_reclaim.sql"
)


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
