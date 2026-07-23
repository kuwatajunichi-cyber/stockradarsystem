"""Contract: Phase 4.5 migration SQL must match registry plan."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M004 = _REPO / "supabase" / "migrations" / "004_phase45_metric_registry.sql"
_M005 = _REPO / "supabase" / "migrations" / "005_phase45_metric_registry_hardening.sql"

_PHASE45_TABLES = (
    "metric_definitions",
    "metric_versions",
    "metric_set_versions",
    "metric_set_members",
    "active_metric_set",
    "derived_object_index",
    "latest_derived_observations",
)

_COMMIT_DERIVED_SIG = "commit_derived_object(uuid, text, bigint, text)"
_TRANSITION_SET_SIG = "transition_metric_set(uuid, text, text)"
_ACTIVATE_CAS_SIG = "activate_metric_set_cas(uuid, uuid, text, bigint)"


@pytest.fixture(name="migration_004")
def fixture_migration_004() -> str:
    raw = _M004.read_bytes()
    if b"\x00" in raw:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


@pytest.fixture(name="migration_005")
def fixture_migration_005() -> str:
    raw = _M005.read_bytes()
    if b"\x00" in raw:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def test_phase45_migration_creates_all_tables(migration_004: str) -> None:
    for table in _PHASE45_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration_004


def test_phase45_migration_rpc_signatures(migration_004: str) -> None:
    assert "CREATE OR REPLACE FUNCTION commit_derived_object" in migration_004
    assert "CREATE OR REPLACE FUNCTION transition_metric_set" in migration_004
    assert "CREATE OR REPLACE FUNCTION activate_metric_set_cas" in migration_004
    assert "GRANT EXECUTE ON FUNCTION activate_metric_set_cas" in migration_004


def test_phase45_migration_rpc_revokes_public_before_grant(migration_004: str) -> None:
    assert "REVOKE ALL ON FUNCTION commit_derived_object(uuid, text, bigint, text) FROM PUBLIC" in migration_004
    assert "REVOKE ALL ON FUNCTION activate_metric_set_cas(uuid, uuid, text, bigint) FROM PUBLIC" in migration_004


def test_phase45_migration_cas_activation_requires_shadow_or_retired(migration_004: str) -> None:
    assert "lifecycle_status IN ('shadow', 'retired')" in migration_004
    assert "lifecycle_status IN ('draft', 'shadow', 'retired')" not in migration_004


def test_phase45_hardening_enables_rls(migration_005: str) -> None:
    for table in _PHASE45_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in migration_005


def test_phase45_hardening_revokes_anon(migration_005: str) -> None:
    for table in _PHASE45_TABLES:
        assert (
            f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated, service_role;"
            in migration_005
        )


def test_phase45_hardening_revokes_service_role_before_grant(migration_005: str) -> None:
    assert "service_role must not UPDATE public." in migration_005
    assert "service_role must not DELETE public." in migration_005
    assert "GRANT SELECT ON TABLE public.active_metric_set TO service_role;" in migration_005
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.active_metric_set" not in migration_005


def test_phase45_hardening_draft_only_metric_set_insert(migration_005: str) -> None:
    assert "enforce_metric_set_versions_insert_draft" in migration_005
    assert "metric_set_versions_insert_draft_only" in migration_005
    assert "metric_set_versions insert must be draft" in migration_005


def test_phase45_hardening_derived_object_pending_insert_only(migration_005: str) -> None:
    assert "GRANT SELECT, INSERT ON TABLE public.derived_object_index TO service_role;" in migration_005
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.derived_object_index" not in migration_005
    assert "enforce_derived_object_index_insert_pending" in migration_005
    assert "service_role must not UPDATE public.derived_object_index" in migration_005


def test_phase45_hardening_metric_set_members_draft_only(migration_005: str) -> None:
    assert "enforce_metric_set_members_insert_draft_set" in migration_005
    assert "metric_set_members_insert_draft_set_only" in migration_005
    assert "metric_set_members insert requires draft set" in migration_005
    assert "FOR UPDATE" in migration_005.split("enforce_metric_set_members_insert_draft_set")[1].split("REVOKE ALL ON FUNCTION public.enforce_metric_set_members")[0]


def test_phase45_hardening_rpc_revoke(migration_005: str) -> None:
    assert "REVOKE ALL ON FUNCTION public.activate_metric_set_cas(" in migration_005
    assert "service_role" in migration_005.split("REVOKE ALL ON FUNCTION public.activate_metric_set_cas")[1].split("GRANT EXECUTE")[0]
    assert "GRANT EXECUTE ON FUNCTION public.activate_metric_set_cas(" in migration_005
    assert "service_role missing EXECUTE on commit_derived_object" in migration_005
    assert "service_role missing EXECUTE on transition_metric_set" in migration_005


def test_phase45_migration_commit_derived_object_fails_on_missing_pending(
    migration_004: str,
) -> None:
    assert "IF NOT FOUND THEN" in migration_004
    assert "pending derived_object_index row not found" in migration_004


def test_phase45_hardening_rejects_residual_grants(migration_005: str) -> None:
    assert "information_schema.role_table_grants" in migration_005
    assert "information_schema.routine_privileges" in migration_005
    assert "Phase 4.5 check failed: residual grant" in migration_005


def test_phase45_migration_seeds_active_metric_set_default_row(migration_004: str) -> None:
    assert "INSERT INTO active_metric_set (pointer_key, metric_set_version_id" in migration_004
    assert "ON CONFLICT (pointer_key) DO NOTHING" in migration_004


def test_phase45_migration_transition_whitelist(migration_004: str) -> None:
    assert "metric_set transition not allowed" in migration_004
    assert "('draft', 'shadow')" in migration_004
    assert "activate_metric_set_cas" in migration_004


def test_phase45_migration_derived_object_key_constraints(migration_004: str) -> None:
    assert "object_key TEXT NOT NULL UNIQUE" not in migration_004
    assert "derived_object_index_pending_object_key" in migration_004
    assert "derived_object_index_snapshot_committed_object_key" in migration_004


def test_phase45_migration_series_recommit_orphans_prior(migration_004: str) -> None:
    assert "IF v_row.object_kind = 'series' THEN" in migration_004
    assert "SET status = 'orphan'" in migration_004
