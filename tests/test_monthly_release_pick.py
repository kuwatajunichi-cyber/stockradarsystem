"""Tests for monthly_release_pick (pure)."""
from __future__ import annotations

from datetime import date

import pytest

from stockradar.universe.monthly_release_pick import (
    parse_monthly_tag,
    pick_monthly_release,
    subtract_calendar_months,
)

pytestmark = pytest.mark.unit


def test_parse_monthly_tag_ok() -> None:
    assert parse_monthly_tag("monthly-20260207-99") == (date(2026, 2, 7), 99)
    assert parse_monthly_tag("  monthly-20260101-1  ") == (date(2026, 1, 1), 1)


def test_parse_monthly_tag_rejects_legacy_and_noise() -> None:
    assert parse_monthly_tag("monthly-20260207") is None
    assert parse_monthly_tag("v1.0.0") is None
    assert parse_monthly_tag("") is None


def test_pick_max_snapshot_not_after_run_date() -> None:
    tags = [
        "monthly-20260301-10",
        "monthly-20260207-5",
        "monthly-20260105-1",
    ]
    p = pick_monthly_release(date(2026, 2, 20), tags)
    assert p.tag == "monthly-20260207-5"
    assert p.universe_resolution == "time_series_ok"
    assert p.reason == ""


def test_pick_same_snapshot_max_run_id() -> None:
    tags = [
        "monthly-20260207-100",
        "monthly-20260207-200",
        "monthly-20260101-1",
    ]
    p = pick_monthly_release(date(2026, 12, 31), tags)
    assert p.tag == "monthly-20260207-200"


def test_pick_fallback_latest_when_all_snapshots_after_run_date() -> None:
    tags = [
        "monthly-20260301-1",
        "monthly-20260215-2",
    ]
    p = pick_monthly_release(date(2026, 1, 1), tags)
    assert p.tag == "monthly-20260301-1"
    assert p.universe_resolution == "fallback_latest"
    assert "2026-01-01" in p.reason


def test_pick_empty_tags_raises() -> None:
    with pytest.raises(ValueError):
        pick_monthly_release(date(2026, 1, 1), [])


def test_pick_no_parsable_tags_raises() -> None:
    with pytest.raises(ValueError):
        pick_monthly_release(date(2026, 1, 1), ["v1", "nope"])


def test_pick_ignores_noise_between_valid() -> None:
    tags = [
        "noise",
        "monthly-20260201-1",
        "other",
    ]
    p = pick_monthly_release(date(2026, 3, 1), tags)
    assert p.tag == "monthly-20260201-1"
    assert p.universe_resolution == "time_series_ok"


def test_subtract_calendar_months() -> None:
    assert subtract_calendar_months(date(2026, 3, 31), 3) == date(2025, 12, 31)
    assert subtract_calendar_months(date(2026, 3, 15), 1) == date(2026, 2, 15)