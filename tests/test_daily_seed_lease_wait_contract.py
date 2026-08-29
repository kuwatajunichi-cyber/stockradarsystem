"""Integration-ish unit: Daily lease trim before begin count."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stockradar.storage.daily_seed_lease import (
    list_active_seed_lease_codes_from_rows,
    wait_and_collect_seed_lease_skips,
)

pytestmark = pytest.mark.unit


def test_list_active_seed_lease_codes_filters_owner_and_expiry() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        {
            "instrument_code": "6758",
            "owner_kind": "series_seed",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        {
            "instrument_code": "7203",
            "owner_kind": "daily_normal",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        {
            "instrument_code": "9984",
            "owner_kind": "series_seed",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
        },
    ]
    assert list_active_seed_lease_codes_from_rows(
        rows, membership_codes=["6758", "7203", "9984"], now=now
    ) == ["6758"]


def test_wait_collect_skips_after_timeout() -> None:
    now0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        {
            "instrument_code": "6758",
            "owner_kind": "series_seed",
            "expires_at": (now0 + timedelta(hours=1)).isoformat(),
        }
    ]
    slept: list[float] = []

    def sleep_fn(s: float) -> None:
        slept.append(s)

    clock = {"t": now0}

    def now_fn():
        return clock["t"]

    def fetch():
        # advance clock on each poll
        clock["t"] = clock["t"] + timedelta(seconds=60)
        return rows

    decision = wait_and_collect_seed_lease_skips(
        membership_codes=["6758", "7203"],
        fetch_active_rows=fetch,
        max_wait_seconds=120.0,
        poll_seconds=60.0,
        sleep_fn=sleep_fn,
        now_fn=now_fn,
    )
    assert "6758" in decision.skipped_codes
    assert "7203" in decision.remaining_codes
    assert "daily_seed_lease_skip" in decision.flags
