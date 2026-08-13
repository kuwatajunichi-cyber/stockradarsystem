"""Contract: Phase 4.5 migration 006 derived generation commit SQL."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M006 = _REPO / "supabase" / "migrations" / "006_phase45_generation_commit.sql"


@pytest.fixture(name="migration_006")
def fixture_migration_006() -> str:
    raw = _M006.read_bytes()
    if b"\x00" in raw:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def test_phase45_migration_006_creates_derived_generation_runs(migration_006: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS derived_generation_runs" in migration_006


def test_phase45_migration_006_source_identity_unique_index(migration_006: str) -> None:
    assert "derived_generation_runs_source_identity" in migration_006
    assert "repository, workflow, github_run_id, metric_set_version_id, trade_date, mode" in migration_006


def test_phase45_migration_006_generation_rpc_signatures(migration_006: str) -> None:
    assert "CREATE OR REPLACE FUNCTION begin_derived_generation" in migration_006
    assert "CREATE OR REPLACE FUNCTION register_pending_derived_object" in migration_006
    assert "CREATE OR REPLACE FUNCTION mark_derived_object_uploaded" in migration_006
    assert "CREATE OR REPLACE FUNCTION heartbeat_derived_generation" in migration_006
    assert "CREATE OR REPLACE FUNCTION commit_derived_generation" in migration_006
    assert "CREATE OR REPLACE FUNCTION mark_derived_generation_failed" in migration_006
    assert "CREATE OR REPLACE FUNCTION list_stale_derived_generations" in migration_006
    assert "CREATE OR REPLACE FUNCTION mark_orphan_object_purged" in migration_006


def test_phase45_migration_006_staging_table(migration_006: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS latest_derived_observations_staging" in migration_006


def test_phase45_migration_006_commit_orphans_prior_snapshots(migration_006: str) -> None:
    assert "SET status = 'orphan'" in migration_006
    assert "d.object_kind = 'snapshot'" in migration_006
    assert "d.object_kind = 'series'" in migration_006


def test_phase45_migration_006_failed_generation_marks_pending_orphan(migration_006: str) -> None:
    assert "mark_derived_generation_failed" in migration_006
    assert "WHERE generation_id = p_generation_id AND status = 'pending'" in migration_006


def test_phase45_migration_006_revokes_legacy_commit_derived_object(migration_006: str) -> None:
    needle = "REVOKE ALL ON FUNCTION public.commit_derived_object(uuid, text, bigint, text)"
    assert needle in migration_006


def test_phase45_migration_006_service_role_grants(migration_006: str) -> None:
    assert "GRANT EXECUTE ON FUNCTION public.begin_derived_generation" in migration_006
    assert "GRANT EXECUTE ON FUNCTION public.commit_derived_generation(uuid, text) TO service_role" in migration_006
    assert "GRANT SELECT, INSERT ON TABLE public.derived_generation_runs TO service_role" in migration_006


def test_phase45_migration_006_generation_coordinate_unique(migration_006: str) -> None:
    assert "derived_object_index_generation_coordinate" in migration_006
    assert "derived_object_index_committed_snapshot_coordinate" in migration_006
    assert "derived_object_index_committed_series_coordinate" in migration_006

def test_phase45_migration_006_uses_valid_postgres_dollar_quoting(migration_006: str) -> None:
    bad_open = "AS " + chr(92) + chr(36) + chr(36)
    bad_close = chr(92) + chr(36) + chr(36) + ";"
    good_open = "AS " + chr(36) + chr(36)
    good_close = chr(36) + chr(36) + ";"
    assert bad_open not in migration_006
    assert bad_close not in migration_006
    assert good_open in migration_006
    assert migration_006.count(good_open) >= 8
    assert migration_006.count(good_close) >= 8
