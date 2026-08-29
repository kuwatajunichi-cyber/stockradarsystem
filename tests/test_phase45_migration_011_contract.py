"""Contract: ADR-005 P1 monthly new-Core migration 011."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M011 = _REPO / "supabase" / "migrations" / "011_adr005_monthly_new_core.sql"


@pytest.fixture(name="migration_011")
def fixture_migration_011() -> str:
    raw = _M011.read_bytes()
    assert bytes([0]) not in raw
    return raw.decode("utf-8")


def test_migration_011_replaces_exact_begin_signature(migration_011: str) -> None:
    assert "DROP FUNCTION IF EXISTS public.begin_derived_generation(" in migration_011
    assert "p_series_coordinates JSONB DEFAULT NULL" in migration_011
    assert "p_expected_prior_logical_digest JSONB DEFAULT NULL" in migration_011
    assert "p_prior_absent JSONB DEFAULT NULL" in migration_011
    assert "GRANT EXECUTE ON FUNCTION public.begin_derived_generation(" in migration_011


def test_migration_011_adds_series_only_contracts(migration_011: str) -> None:
    for token in (
        "series_seed",
        "series_repair",
        "series_only",
        "series_seed_delta",
        "series_repair_delta",
        "superseded",
        "derived_generation_series_cas",
    ):
        assert token in migration_011
    assert "derived_object_index_committed_series_coordinate" in migration_011
    assert "p_expected_old_digest is invalid for series_only" in migration_011
    assert "SET status = 'superseded'" in migration_011


def test_migration_011_restores_commit_timeout(migration_011: str) -> None:
    assert "SET statement_timeout = '180s'" in migration_011
    assert (
        "ALTER FUNCTION public.commit_derived_generation(uuid, text, text)"
        in migration_011
    )


def test_migration_011_keeps_legacy_cache_rpc_untouched(migration_011: str) -> None:
    assert "ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1" in migration_011
    assert "commit_cache_pointer_cas" in migration_011
    assert "CREATE OR REPLACE FUNCTION commit_jpx_url_cache" not in migration_011
    assert "CREATE OR REPLACE FUNCTION public.commit_jpx_url_cache" not in migration_011


def test_migration_011_control_tables_are_rls_protected(migration_011: str) -> None:
    for table in (
        "adr005_runtime_config",
        "monthly_new_core_backfill_requests",
        "request_release_links",
        "monthly_new_core_backfill_events",
        "monthly_new_core_backfill_outbox",
        "monthly_new_core_series_repairs",
    ):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration_011
        assert f"REVOKE ALL ON TABLE public.{table}" in migration_011


def test_migration_011_advisory_locks_use_single_bigint(migration_011: str) -> None:
    assert "pg_advisory_xact_lock(hashtextextended(" in migration_011
    assert "pg_advisory_xact_lock(\n        hashtextextended(" in migration_011
    assert "pg_advisory_xact_lock(\n    hashtextextended(" in migration_011
