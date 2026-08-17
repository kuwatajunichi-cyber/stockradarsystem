"""Contract: Phase 4.5 migration 009 manifest kinds + commit expectations."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M009 = _REPO / "supabase" / "migrations" / "009_phase45_manifest_kinds_and_commit.sql"


@pytest.fixture(name="migration_009")
def fixture_migration_009() -> str:
    raw = _M009.read_bytes()
    assert b"\x00" not in raw, "migration 009 must be UTF-8 without NUL bytes"
    text = raw.decode("utf-8")
    assert "AS $$" in text
    return text


def test_phase45_migration_009_expands_object_kinds(migration_009: str) -> None:
    assert "snapshot_manifest" in migration_009
    assert "series_manifest" in migration_009
    assert "derived_object_index_object_kind_check" in migration_009


def test_phase45_migration_009_requires_expected_digests(migration_009: str) -> None:
    assert "expected_object_count is required" in migration_009
    assert "expected_object_set_digest is required" in migration_009
    assert "set_pending_generation_object_set_digest" in migration_009


def test_phase45_migration_009_clears_staging_and_orphans_manifests(migration_009: str) -> None:
    assert "DELETE FROM latest_derived_observations_staging" in migration_009
    assert "object_kind IN ('snapshot', 'snapshot_manifest')" in migration_009
    assert "object_kind IN ('series', 'series_manifest')" in migration_009


def test_phase45_migration_009_grants_service_role_only(migration_009: str) -> None:
    assert (
        "REVOKE ALL ON FUNCTION public.set_pending_generation_object_set_digest(uuid, text)"
        in migration_009
    )
    assert (
        "GRANT EXECUTE ON FUNCTION public.set_pending_generation_object_set_digest(uuid, text)"
        in migration_009
    )
