"""Contract: ADR-005 P5 progress / repair RPC migration 013."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_M013 = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "013_adr005_series_seed_progress.sql"


def test_migration_013_progress_and_repair() -> None:
    raw = _M013.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    assert "commit_trade_date_progress" in text
    assert "commit_series_repair" in text
    assert "self-approval forbidden" in text
    assert "GRANT EXECUTE ON FUNCTION public.commit_trade_date_progress" in text
