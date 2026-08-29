"""Contract: ADR-005 P3 monthly commit RPC migration 012."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_M012 = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "012_adr005_monthly_commit_rpc.sql"


@pytest.fixture(name="migration_012")
def fixture_migration_012() -> str:
    raw = _M012.read_bytes()
    assert bytes([0]) not in raw
    return raw.decode("utf-8")


def test_migration_012_defines_commit_rpc(migration_012: str) -> None:
    assert "commit_monthly_snapshot_with_backfill_request" in migration_012
    assert "list_committed_monthly_snapshot_rows" in migration_012
    assert "get_adr005_feature_start_release_month" in migration_012
    assert "only identity (0,1)" in migration_012
    assert "noncanonical_loser" in migration_012
    assert "GRANT EXECUTE ON FUNCTION public.commit_monthly_snapshot_with_backfill_request" in migration_012


def test_migration_012_locks_release_month_and_handles_loser(migration_012: str) -> None:
    assert "mnc:" in migration_012
    assert "noncanonical_loser" in migration_012
    assert "canonical_winner" in migration_012
    assert "pg_advisory_xact_lock(hashtextextended(" in migration_012
