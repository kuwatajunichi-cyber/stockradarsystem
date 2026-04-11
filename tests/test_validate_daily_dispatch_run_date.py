"""validate_daily_dispatch_run_date pure validation tests."""
from __future__ import annotations

from datetime import date

import pytest

from stockradar.jobs import validate_daily_dispatch_run_date as v


def test_empty_input_is_not_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v, "_today_tokyo", lambda: date(2026, 4, 10))
    assert v.validate_input("") == (False, None)
    assert v.validate_input("  ") == (False, None)


def test_today_tokyo_is_not_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v, "_today_tokyo", lambda: date(2026, 4, 10))
    assert v.validate_input("2026-04-10") == (False, date(2026, 4, 10))


def test_past_within_three_months_is_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v, "_today_tokyo", lambda: date(2026, 4, 10))
    is_rep, d = v.validate_input("2026-02-15")
    assert is_rep is True
    assert d == date(2026, 2, 15)


def test_future_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v, "_today_tokyo", lambda: date(2026, 4, 10))
    with pytest.raises(ValueError, match="future|after"):
        v.validate_input("2026-12-31")


def test_too_old_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v, "_today_tokyo", lambda: date(2026, 4, 10))
    with pytest.raises(ValueError, match="3 calendar months"):
        v.validate_input("2025-12-31")