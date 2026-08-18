"""Contract: Phase 4.5 migration 010 commit statement_timeout."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M010 = _REPO / "supabase" / "migrations" / "010_phase45_commit_statement_timeout.sql"


@pytest.fixture(name="migration_010")
def fixture_migration_010() -> str:
    raw = _M010.read_bytes()
    assert b"\x00" not in raw, "migration 010 must be UTF-8 without NUL bytes"
    text = raw.decode("utf-8")
    assert "BEGIN;" in text
    assert "COMMIT;" in text
    return text


def test_phase45_migration_010_sets_commit_statement_timeout(migration_010: str) -> None:
    assert "ALTER FUNCTION public.commit_derived_generation(uuid, text, text)" in migration_010
    assert "SET statement_timeout = '180s'" in migration_010


def test_phase45_migration_010_timeout_matches_client_floor(migration_010: str) -> None:
    from stockradar.storage.supabase_metric_generation import SupabaseMetricGenerationAdapter

    assert SupabaseMetricGenerationAdapter.COMMIT_RPC_TIMEOUT_S >= 180.0
    assert "180s" in migration_010
