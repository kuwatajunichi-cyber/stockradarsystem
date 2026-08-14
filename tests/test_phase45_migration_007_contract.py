"""Contract: Phase 4.5 migration 007 commit expected_old_digest CAS SQL."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M007 = _REPO / "supabase" / "migrations" / "007_phase45_commit_expected_old_digest.sql"


@pytest.fixture(name="migration_007")
def fixture_migration_007() -> str:
    raw = _M007.read_bytes()
    assert b"\x00" not in raw, "migration 007 must be UTF-8 without NUL bytes"
    return raw.decode("utf-8")


def test_phase45_migration_007_drops_two_arg_commit(migration_007: str) -> None:
    assert "DROP FUNCTION IF EXISTS public.commit_derived_generation(uuid, text);" in migration_007


def test_phase45_migration_007_adds_expected_old_digest_param(migration_007: str) -> None:
    assert "p_expected_old_digest TEXT DEFAULT NULL" in migration_007
    assert "expected_old_digest mismatch" in migration_007
    assert "expected_old_digest provided but no committed snapshot" in migration_007


def test_phase45_migration_007_grants_three_arg_signature(migration_007: str) -> None:
    needle = "GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text, text) TO service_role;"
    assert needle in migration_007
    assert "REVOKE ALL ON FUNCTION public.commit_derived_generation(uuid, text, text)" in migration_007
