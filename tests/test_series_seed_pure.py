"""Unit tests for ADR-005 series_seed pure helpers."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stockradar.jobs.write_series_only_generation import plan_series_only_trade_date
from stockradar.metrics.registry_spec import (
    load_metric_set_spec,
    require_seed_metric_input_contract,
)
from stockradar.storage.derived_series import merge_missing_dates_only
from stockradar.storage.series_seed import (
    HistoryQualityInput,
    aggregate_history_quality,
    series_only_expected_object_count,
    validate_series_repair_approver,
)
from stockradar.utils.yf_cache_long_history import fetch_long_history_bounded

pytestmark = pytest.mark.unit


def test_catalog_seed_contract_present_fingerprints_stable() -> None:
    spec = load_metric_set_spec()
    require_seed_metric_input_contract(spec)
    # fingerprint path unchanged: reload twice
    assert load_metric_set_spec().set_fingerprint == spec.set_fingerprint


def test_merge_missing_dates_only_skips_existing() -> None:
    dates, series, flags, wrote = merge_missing_dates_only(
        trade_date="2026-08-01",
        metric_keys_ordered=["m1"],
        values={"m1": 1.0},
        prior_dates=["2026-08-01"],
        prior_series={"m1": [9.0]},
        prior_flags=[{"missing": False}],
    )
    assert wrote is False
    assert series["m1"] == [9.0]
    dates2, series2, _, wrote2 = merge_missing_dates_only(
        trade_date="2026-08-02",
        metric_keys_ordered=["m1"],
        values={"m1": 2.0},
        prior_dates=dates,
        prior_series=series,
        prior_flags=flags,
    )
    assert wrote2 is True
    assert dates2 == ["2026-08-01", "2026-08-02"]
    assert series2["m1"] == [9.0, 2.0]


def test_bounded_fetch_uses_window() -> None:
    calls: list[tuple[datetime, datetime]] = []

    def fetch_chunk(start: datetime, end: datetime):
        calls.append((start, end))
        import pandas as pd

        return pd.DataFrame({"Close": [1.0]}, index=[start])

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    df = fetch_long_history_bounded(
        required_input_start=start,
        coverage_end=end,
        fetch_chunk=fetch_chunk,
        warmup_calendar_days=7,
    )
    assert not df.empty
    assert calls
    # first chunk should start at or before required_input_start - warmup
    assert calls[0][0] <= start


def test_history_quality_not_applicable_before_enable() -> None:
    body = aggregate_history_quality(
        HistoryQualityInput(
            release_month="2026-08",
            feature_start_release_month=None,
            request_statuses=(),
        )
    )
    assert body["tier"] == "not_applicable"


def test_series_repair_rejects_self_approval() -> None:
    with pytest.raises(PermissionError):
        validate_series_repair_approver(
            approver_github_login="alice",
            worker_github_actor="Alice",
        )


def test_series_only_expected_count() -> None:
    assert series_only_expected_object_count(0) == 0
    assert series_only_expected_object_count(3) == 7


def test_plan_trade_date_skips_existing() -> None:
    plan = plan_series_only_trade_date(
        request_id="mnc-v1-" + ("ab" * 32),
        mode="series_seed",
        trade_date="2026-08-01",
        candidate_codes=["7203", "9984"],
        existing_dates_by_code={"7203": ["2026-08-01"]},
    )
    assert plan.write_codes == ("9984",)
    assert plan.resolved_noop_codes == ("7203",)
    assert plan.expected_object_count == 3
