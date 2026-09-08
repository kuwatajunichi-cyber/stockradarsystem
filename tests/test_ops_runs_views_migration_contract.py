"""Contract: 5.5b ops runs views are service_role SELECT only."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_M018 = _REPO / "supabase" / "migrations" / "018_ops_runs_views.sql"
_M019 = _REPO / "supabase" / "migrations" / "019_download_grants_issued_request_id.sql"
_CONTRACT = _REPO / "docs" / "contracts" / "ops_runs_views.md"


@pytest.fixture(name="migration_018")
def fixture_migration_018() -> str:
    raw = _M018.read_bytes()
    assert b"\x00" not in raw, "migration 018 must be UTF-8 without NUL bytes"
    return raw.decode("utf-8")


def test_creates_ops_views(migration_018: str) -> None:
    assert "CREATE OR REPLACE VIEW public.ops_runs_by_day" in migration_018
    assert "CREATE OR REPLACE VIEW public.ops_runs_success_rate_30d" in migration_018
    assert "DO $$" in migration_018
    assert "END $$;" in migration_018
    assert "FROM public.runs" in migration_018
    assert "success_rate" in migration_018
    assert "started_at_utc >= now() - interval '30 days'" in migration_018
    assert "(now() AT TIME ZONE 'utc')" not in migration_018


def test_p0_no_anon_grants_or_policies(migration_018: str) -> None:
    for view in ("ops_runs_by_day", "ops_runs_success_rate_30d"):
        assert (
            f"REVOKE ALL ON TABLE public.{view} FROM PUBLIC, anon, authenticated;"
            in migration_018
        )
        assert f"GRANT SELECT ON TABLE public.{view} TO service_role;" in migration_018
    assert "GRANT INSERT" not in migration_018
    assert "GRANT UPDATE" not in migration_018
    assert "GRANT DELETE" not in migration_018
    assert "CREATE POLICY" not in migration_018
    assert "pg_policies" in migration_018


def test_not_a_user_dashboard(migration_018: str) -> None:
    assert "Not a user dashboard" in migration_018 or "user dashboard" in migration_018.lower()


def test_contract_doc_exists() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")
    assert "ops_runs_views" in text
    assert "ops_runs_by_day" in text
    assert "ops_runs_success_rate_30d" in text
    assert "service_role" in text
    assert "Web UI" in text or "user dashboard" in text.lower()
    assert "019_download_grants_issued_request_id.sql" in text


def test_019_repeats_timestamptz_safe_30d_window() -> None:
    sql = _M019.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW public.ops_runs_success_rate_30d" in sql
    assert "started_at_utc >= now() - interval '30 days'" in sql
    assert "(now() AT TIME ZONE 'utc')" not in sql
