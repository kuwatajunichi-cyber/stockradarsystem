"""Contract: P0 hardening migration SQL must match security plan."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_MIGRATION = _REPO / "supabase" / "migrations" / "003_p0_control_plane_hardening.sql"

_CONTROL_PLANE_TABLES = (
    "runs",
    "artifact_index",
    "cache_index",
    "cache_pointers",
    "monthly_snapshots",
    "publish_status",
)

_COMMIT_FIXED_CACHE_SIG = "commit_fixed_cache(text, text, text, bigint, text, bigint, uuid)"
_COMMIT_JPX_URL_CACHE_SIG = "commit_jpx_url_cache(text, text, bigint, text, bigint, uuid)"

_ADAPTER_METHODS_COMMENT_MARKERS = (
    "upsert_run",
    "get_run",
    "update_run",
    "insert_artifact_index_pending",
    "commit_artifact_index",
    "mark_artifact_index_orphan",
    "list_orphan_rows",
    "delete_row",
    "insert_cache_index_pending_fixed",
    "upsert_cache_index_pending_patched",
    "commit_cache_index_patched",
    "get_cache_index_patched",
    "get_patched_cache_row",
    "list_patched_cache_rows",
    "mark_cache_index_orphan",
    "get_cache_pointer",
    "insert_monthly_snapshot_pending",
    "commit_monthly_snapshot",
    "mark_monthly_snapshot_orphan",
    "list_committed_monthly_tags",
    "insert_publish_status_pending",
    "commit_publish_status",
    "mark_publish_status_orphan",
    "get_publish_status",
    "commit_fixed_cache",
    "commit_jpx_url_cache",
)


@pytest.fixture(name="migration_sql")
def fixture_migration_sql() -> str:
    assert _MIGRATION.is_file(), f"missing migration: {_MIGRATION}"
    raw = _MIGRATION.read_bytes()
    if b"\x00" in raw:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def test_p0_migration_enables_rls_on_all_control_plane_tables(migration_sql: str) -> None:
    for table in _CONTROL_PLANE_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in migration_sql


def test_p0_migration_revokes_non_privileged_table_grants(migration_sql: str) -> None:
    for table in _CONTROL_PLANE_TABLES:
        assert (
            f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated;" in migration_sql
        )


def test_p0_migration_grants_service_role_crud(migration_sql: str) -> None:
    for table in _CONTROL_PLANE_TABLES:
        assert (
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO service_role;"
            in migration_sql
        )


def test_p0_migration_rpc_signatures_fixed(migration_sql: str) -> None:
    assert _COMMIT_FIXED_CACHE_SIG in migration_sql
    assert _COMMIT_JPX_URL_CACHE_SIG in migration_sql
    assert "REVOKE ALL ON FUNCTION public.commit_fixed_cache(" in migration_sql
    assert "REVOKE ALL ON FUNCTION public.commit_jpx_url_cache(" in migration_sql
    assert "GRANT EXECUTE ON FUNCTION public.commit_fixed_cache(" in migration_sql
    assert "GRANT EXECUTE ON FUNCTION public.commit_jpx_url_cache(" in migration_sql


def test_p0_migration_default_privileges_for_measured_owners(migration_sql: str) -> None:
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public" in migration_sql
    assert "REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;" in migration_sql
    assert "REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;" in migration_sql
    assert "REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;" in migration_sql
    assert "defaclrole::regrole::text = 'postgres'" in migration_sql


def test_p0_migration_self_check_covers_service_role_and_non_privileged(migration_sql: str) -> None:
    assert "has_table_privilege('service_role'" in migration_sql
    assert "has_function_privilege(" in migration_sql
    assert "rolbypassrls" in migration_sql
    assert "information_schema.role_table_grants" in migration_sql
    assert "information_schema.routine_privileges" in migration_sql
    assert "pg_default_acl" in migration_sql
    assert "pg_policies" in migration_sql


def test_p0_migration_documents_adapter_grant_map(migration_sql: str) -> None:
    for marker in _ADAPTER_METHODS_COMMENT_MARKERS:
        assert marker in migration_sql
