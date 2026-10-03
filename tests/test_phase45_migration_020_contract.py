"""Contract: migration 020 deletes orphan derived_object_index rows only."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M020 = _REPO / "supabase" / "migrations" / "020_delete_orphan_derived_objects.sql"


@pytest.fixture(name="migration_020")
def fixture_migration_020() -> str:
    raw = _M020.read_bytes()
    assert b"\x00" not in raw, "migration 020 must be UTF-8 without NUL bytes"
    return raw.decode("utf-8")


def test_delete_orphan_rpc_signature_and_status_filter(migration_020: str) -> None:
    assert "CREATE OR REPLACE FUNCTION public.delete_orphan_derived_objects(p_limit integer)" in (
        migration_020
    )
    assert "WHERE status = 'orphan'" in migration_020
    assert "committed" not in migration_020.split("WHERE status = 'orphan'")[1][:200]


def test_delete_orphan_rpc_grants_service_role_only(migration_020: str) -> None:
    assert (
        "REVOKE ALL ON FUNCTION public.delete_orphan_derived_objects(integer)"
        in migration_020
    )
    assert (
        "GRANT EXECUTE ON FUNCTION public.delete_orphan_derived_objects(integer) TO service_role;"
        in migration_020
    )
    assert "GRANT EXECUTE" in migration_020
    assert "TO anon" not in migration_020
    assert "TO authenticated" not in migration_020


def test_delete_orphan_rpc_caps_limit_and_timeout(migration_020: str) -> None:
    assert "LEAST(p_limit, 20000)" in migration_020
    assert "SET statement_timeout = '120s'" in migration_020
    assert "SECURITY DEFINER" in migration_020
