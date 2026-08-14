"""Contract: Phase 4.5 migration 008 batch object RPCs."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M008 = _REPO / "supabase" / "migrations" / "008_phase45_batch_object_rpcs.sql"


@pytest.fixture(name="migration_008")
def fixture_migration_008() -> str:
    raw = _M008.read_bytes()
    assert b"\x00" not in raw, "migration 008 must be UTF-8 without NUL bytes"
    text = raw.decode("utf-8")
    assert "AS $$" in text
    assert text.count("$$;") >= 3
    return text


def test_phase45_migration_008_defines_batch_functions(migration_008: str) -> None:
    assert "CREATE OR REPLACE FUNCTION register_pending_derived_objects(" in migration_008
    assert "CREATE OR REPLACE FUNCTION mark_derived_objects_uploaded(" in migration_008
    assert "CREATE OR REPLACE FUNCTION stage_latest_derived_observations(" in migration_008


def test_phase45_migration_008_sets_function_statement_timeout(migration_008: str) -> None:
    assert migration_008.count("SET statement_timeout = '60s'") == 3


def test_phase45_migration_008_reuse_and_conflict_use_logical_digest(migration_008: str) -> None:
    assert "v_existing.logical_digest = v_digest" in migration_008
    assert "coordinate conflict" in migration_008
    assert "duplicate coordinate in chunk" in migration_008


def test_phase45_migration_008_mark_rejects_partial_success(migration_008: str) -> None:
    assert "count mismatch expected" in migration_008


def test_phase45_migration_008_grants_service_role_only(migration_008: str) -> None:
    for name in (
        "register_pending_derived_objects(uuid, jsonb)",
        "mark_derived_objects_uploaded(uuid, jsonb)",
        "stage_latest_derived_observations(uuid, jsonb)",
    ):
        assert f"REVOKE ALL ON FUNCTION public.{name}" in migration_008
        assert f"GRANT EXECUTE ON FUNCTION public.{name} TO service_role;" in migration_008


def test_phase45_migration_008_documents_chunk_contract(migration_008: str) -> None:
    assert "500" in migration_008
    assert "Client MUST chunk" in migration_008
