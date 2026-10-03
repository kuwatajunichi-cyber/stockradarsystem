"""Contract: Track C entitlements / preferences DDL inherits P0."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M021 = _REPO / "supabase" / "migrations" / "021_entitlements_preferences.sql"


@pytest.fixture(name="migration_021")
def fixture_migration_021() -> str:
    raw = _M021.read_bytes()
    assert b"\x00" not in raw, "migration 021 must be UTF-8 without NUL bytes"
    return raw.decode("utf-8")


def test_creates_entitlements_and_preferences(migration_021: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS public.entitlements" in migration_021
    assert "CREATE TABLE IF NOT EXISTS public.user_preferences" in migration_021
    assert "operator" in migration_021
    assert "internal_beta" in migration_021
    assert "external_paid" not in migration_021
    assert "external_free" not in migration_021
    assert "schema_version" in migration_021
    assert "user_preferences_bag_size" in migration_021
    assert "65536" in migration_021
    assert "CREATE POLICY" not in migration_021
    assert "GRANT EXECUTE" not in migration_021
    assert "webhook" not in migration_021.lower() or "No webhook" in migration_021


def test_p0_rls_revoke_service_role_only(migration_021: str) -> None:
    assert "ALTER TABLE public.entitlements ENABLE ROW LEVEL SECURITY" in migration_021
    assert "ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY" in migration_021
    assert (
        "REVOKE ALL ON TABLE public.entitlements FROM PUBLIC, anon, authenticated;"
        in migration_021
    )
    assert (
        "REVOKE ALL ON TABLE public.user_preferences FROM PUBLIC, anon, authenticated;"
        in migration_021
    )
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.entitlements TO service_role;" in (
        migration_021
    )
    assert (
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.user_preferences TO service_role;"
        in migration_021
    )
    assert "pg_policies" in migration_021
    assert "DO $$" in migration_021
