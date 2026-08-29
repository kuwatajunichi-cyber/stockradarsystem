"""Unit tests for Daily seed lease skip membership trim."""
from __future__ import annotations

import pytest

from stockradar.storage.daily_seed_lease import filter_membership_after_seed_lease_wait
from stockradar.storage.derived_generation import (
    ArtifactProfile,
    expected_derived_object_count,
)

pytestmark = pytest.mark.unit


def test_lease_skip_trims_before_begin_count() -> None:
    decision = filter_membership_after_seed_lease_wait(
        membership_codes=["7203", "6758", "9984"],
        active_seed_lease_codes=["6758"],
        waited_seconds=120.0,
        max_wait_seconds=120.0,
    )
    assert decision.skipped_codes == ("6758",)
    assert decision.remaining_codes == ("7203", "9984")
    assert decision.flags == ("daily_seed_lease_skip",)
    count = expected_derived_object_count(
        profile=ArtifactProfile.SNAPSHOT_SERIES_LATEST,
        instrument_count=len(decision.remaining_codes),
    )
    assert count == expected_derived_object_count(
        profile=ArtifactProfile.SNAPSHOT_SERIES_LATEST,
        instrument_count=2,
    )


def test_lease_skip_no_trim_before_timeout() -> None:
    decision = filter_membership_after_seed_lease_wait(
        membership_codes=["7203", "6758"],
        active_seed_lease_codes=["6758"],
        waited_seconds=30.0,
        max_wait_seconds=120.0,
    )
    assert decision.skipped_codes == ()
    assert decision.remaining_codes == ("7203", "6758")
    assert decision.flags == ()
    assert decision.waited_seconds == 30.0


def test_wait_and_collect_uses_active_filter_not_raw_rows() -> None:
    from datetime import datetime, timezone, timedelta

    from stockradar.storage.daily_seed_lease import wait_and_collect_seed_lease_skips

    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    expired = (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    active = (now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    rows = [
        {"instrument_code": "6758", "owner_kind": "series_seed", "expires_at": expired},
        {"instrument_code": "9984", "owner_kind": "series_seed", "expires_at": active},
    ]
    decision = wait_and_collect_seed_lease_skips(
        membership_codes=["7203", "6758", "9984"],
        fetch_active_rows=lambda: rows,
        max_wait_seconds=0.0,
        poll_seconds=0.0,
        sleep_fn=lambda _s: None,
        now_fn=lambda: now,
    )
    assert decision.skipped_codes == ("9984",)
    assert "6758" not in decision.skipped_codes
    assert decision.remaining_codes == ("7203", "6758")
