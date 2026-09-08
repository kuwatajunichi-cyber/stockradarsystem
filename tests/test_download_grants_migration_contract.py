"""Contract: download_grants DDL inherits P0 hardening."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M017 = _REPO / "supabase" / "migrations" / "017_download_grants.sql"


@pytest.fixture(name="migration_017")
def fixture_migration_017() -> str:
    raw = _M017.read_bytes()
    assert b"\x00" not in raw, "migration 017 must be UTF-8 without NUL bytes"
    return raw.decode("utf-8")


def test_creates_download_grants(migration_017: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS public.download_grants" in migration_017
    assert "mint_result" in migration_017
    assert "reason_code" in migration_017
    assert "request_id" in migration_017
    assert "signed_url" not in migration_017.lower().replace(
        "download_grants_no_signed_url_column", ""
    ) or "do not store signed url" in migration_017.lower()


def test_p0_rls_revoke_no_user_policies(migration_017: str) -> None:
    assert "ALTER TABLE public.download_grants ENABLE ROW LEVEL SECURITY" in migration_017
    assert (
        "REVOKE ALL ON TABLE public.download_grants FROM PUBLIC, anon, authenticated;"
        in migration_017
    )
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.download_grants TO service_role;" in (
        migration_017
    )
    assert "download_grants_issued_request_id" in migration_017
    assert "WHERE mint_result = 'issued'" in migration_017
    assert "pg_policies" in migration_017
    assert "tablename = 'download_grants'" in migration_017
    assert "anon" in migration_017
    assert "authenticated" in migration_017
    assert "CREATE POLICY" not in migration_017.upper().replace(
        "UNEXPECTED RLS POLICIES", ""
    )


def test_no_execute_grant_to_anon(migration_017: str) -> None:
    assert "GRANT EXECUTE" not in migration_017
    assert "CREATE POLICY" not in migration_017


def test_issued_denied_check(migration_017: str) -> None:
    assert "DO $$" in migration_017
    assert "END $$;" in migration_017
