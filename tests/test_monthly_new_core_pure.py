"""Unit tests for ADR-005 monthly new-core pure helpers."""
from __future__ import annotations

import pytest

from stockradar.storage.monthly_new_core import (
    CommittedMonthlySnapshotRow,
    build_request_id_v1,
    canonical_release_for_month,
    core_delta,
    current_core_logical_digest,
    previous_core_row_for_release_month,
    previous_month_key,
)

pytestmark = pytest.mark.unit


def test_core_delta_sorted_unique() -> None:
    assert core_delta(previous_codes=["7203", "6758"], current_codes=["7203", "9984", "6758"]) == [
        "9984"
    ]
    assert core_delta(previous_codes=["7203"], current_codes=["7203"]) == []


def test_current_core_logical_digest_stable() -> None:
    a = current_core_logical_digest(["7203", "6758"])
    b = current_core_logical_digest(["6758", "7203", "7203"])
    assert a == b
    assert len(a) == 64


def test_canonical_release_for_month_last_wins_no_fallback() -> None:
    rows = [
        CommittedMonthlySnapshotRow(
            monthly_tag="monthly-20260801-1",
            snapshot_date="2026-08-01",
            github_run_id=1,
            object_keys={"core": {"object_key": "monthly/a/core.csv"}},
        ),
        CommittedMonthlySnapshotRow(
            monthly_tag="monthly-20260801-9",
            snapshot_date="2026-08-01",
            github_run_id=9,
            object_keys={"core": {"object_key": "monthly/b/core.csv"}},
        ),
        CommittedMonthlySnapshotRow(
            monthly_tag="monthly-20260701-3",
            snapshot_date="2026-07-01",
            github_run_id=3,
            object_keys={"core": {"object_key": "monthly/c/core.csv"}},
        ),
    ]
    winner = canonical_release_for_month("2026-08", rows)
    assert winner is not None
    assert winner.monthly_tag == "monthly-20260801-9"
    assert canonical_release_for_month("2026-09", rows) is None


def test_previous_core_row_uses_prior_calendar_month() -> None:
    rows = [
        CommittedMonthlySnapshotRow(
            monthly_tag="monthly-20260801-30679139304",
            snapshot_date="2026-08-01",
            github_run_id=30679139304,
            object_keys={
                "core": {
                    "object_key": "monthly/monthly-20260801-30679139304/equity_domestic_core_with_name.csv"
                }
            },
        )
    ]
    assert previous_month_key("2026-09") == "2026-08"
    prev = previous_core_row_for_release_month("2026-09", rows)
    assert prev is not None
    assert prev.monthly_tag.endswith("30679139304")


def test_build_request_id_v1_unpartitioned() -> None:
    rid = build_request_id_v1(
        release_month="2026-09",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest_hex="a" * 64,
        metric_set_version_id="13209d23-0000-4000-8000-000000000001",
        added_codes=["9984"],
    )
    assert rid.startswith("mnc-v1-")
    assert len(rid) == len("mnc-v1-") + 64


def test_decide_noop_empty_delta() -> None:
    from stockradar.storage.monthly_new_core import decide_monthly_backfill_outcome

    prev = CommittedMonthlySnapshotRow(
        monthly_tag="monthly-20260801-1",
        snapshot_date="2026-08-01",
        github_run_id=1,
        object_keys={"core": {"object_key": "monthly/a/core.csv"}},
    )
    d = decide_monthly_backfill_outcome(
        release_month="2026-09",
        feature_start_release_month="2026-09",
        previous_row=prev,
        current_codes=["7203"],
        previous_codes=["7203"],
        expected_trade_dates=["2026-08-01"],
    )
    assert d.outcome == "noop"
    assert d.added_codes == ()


def test_decide_blocked_missing_previous() -> None:
    from stockradar.storage.monthly_new_core import decide_monthly_backfill_outcome

    d = decide_monthly_backfill_outcome(
        release_month="2026-09",
        feature_start_release_month="2026-09",
        previous_row=None,
        current_codes=["7203"],
        previous_codes=None,
        expected_trade_dates=[],
    )
    assert d.outcome == "blocked"
    assert d.reason_code == "missing_previous_core"


def test_decide_runnable() -> None:
    from stockradar.storage.monthly_new_core import decide_monthly_backfill_outcome

    prev = CommittedMonthlySnapshotRow(
        monthly_tag="monthly-20260801-1",
        snapshot_date="2026-08-01",
        github_run_id=1,
        object_keys={"core": {"object_key": "monthly/a/core.csv"}},
    )
    d = decide_monthly_backfill_outcome(
        release_month="2026-09",
        feature_start_release_month="2026-09",
        previous_row=prev,
        current_codes=["7203", "9984"],
        previous_codes=["7203"],
        expected_trade_dates=["2026-08-01", "2026-08-02"],
    )
    assert d.outcome == "runnable"
    assert d.added_codes == ("9984",)


def test_decide_blocked_coverage_empty() -> None:
    from stockradar.storage.monthly_new_core import decide_monthly_backfill_outcome

    prev = CommittedMonthlySnapshotRow(
        monthly_tag="monthly-20260801-1",
        snapshot_date="2026-08-01",
        github_run_id=1,
        object_keys={"core": {"object_key": "monthly/a/core.csv"}},
    )
    d = decide_monthly_backfill_outcome(
        release_month="2026-09",
        feature_start_release_month="2026-09",
        previous_row=prev,
        current_codes=["7203", "9984"],
        previous_codes=["7203"],
        expected_trade_dates=[],
    )
    assert d.outcome == "blocked"
    assert d.reason_code == "coverage_empty"
    assert d.added_codes == ("9984",)
