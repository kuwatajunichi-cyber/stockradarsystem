"""Contract: Phase 4.5 series merge + year accumulation."""
from __future__ import annotations

import pytest

from stockradar.jobs.write_derived_generation import (
    DerivedGenerationRequest,
    SnapshotInput,
    run_derived_generation,
)
from stockradar.storage.derived_generation import FakeMetricGenerationStore
from stockradar.storage.derived_series import (
    gunzip_series_bytes,
    merge_trade_date_into_series,
    parse_series_canonical_bytes,
)
from stockradar.storage.r2_object_store import FakeR2ObjectStore

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
SHA = "c" * 64


@pytest.mark.unit
def test_merge_trade_date_into_series_appends_new_date() -> None:
    dates, series, flags = merge_trade_date_into_series(
        trade_date="2026-01-16",
        metric_keys_ordered=["alpha_metric"],
        values={"alpha_metric": 2.0},
        prior_dates=["2026-01-15"],
        prior_series={"alpha_metric": [1.0]},
        prior_flags=[{}],
    )
    assert dates == ["2026-01-15", "2026-01-16"]
    assert series["alpha_metric"] == [1.0, 2.0]
    assert flags == [{}, {}]


@pytest.mark.unit
def test_merge_trade_date_into_series_replaces_existing_date() -> None:
    dates, series, flags = merge_trade_date_into_series(
        trade_date="2026-01-15",
        metric_keys_ordered=["alpha_metric"],
        values={"alpha_metric": 9.0},
        prior_dates=["2026-01-15"],
        prior_series={"alpha_metric": [1.0]},
        prior_flags=[{}],
    )
    assert dates == ["2026-01-15"]
    assert series["alpha_metric"] == [9.0]
    assert flags == [{}]


@pytest.mark.unit
def test_run_derived_generation_accumulates_series_across_runs() -> None:
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    values_day1 = {"1301": {"alpha_metric": 1.0}}
    values_day2 = {"1301": {"alpha_metric": 2.0}}
    snapshot_input_day1 = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values_day1,
        layer1_input_fingerprint=SHA,
    )
    snapshot_input_day2 = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values_day2,
        layer1_input_fingerprint=SHA,
    )
    request_day1 = DerivedGenerationRequest(
        stage="4.5b",
        mode="normal",
        trade_date="2026-01-15",
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=1,
        metric_set_version_id=SET_ID,
        active_metric_set_id=None,
        lifecycle_status="shadow",
        is_active=False,
        is_current_latest_trade_date=False,
    )
    result1 = run_derived_generation(
        request_day1,
        snapshot_input=snapshot_input_day1,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    assert result1.exit_code == 0

    request_day2 = DerivedGenerationRequest(
        stage="4.5b",
        mode="normal",
        trade_date="2026-01-16",
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=2,
        metric_set_version_id=SET_ID,
        active_metric_set_id=None,
        lifecycle_status="shadow",
        is_active=False,
        is_current_latest_trade_date=False,
    )
    result2 = run_derived_generation(
        request_day2,
        snapshot_input=snapshot_input_day2,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    assert result2.exit_code == 0

    object_key = generation_store.get_committed_series_object_key(
        metric_set_version_id=SET_ID,
        instrument_code="1301",
        series_year=2026,
    )
    assert object_key is not None
    dates, series, _flags = parse_series_canonical_bytes(
        gunzip_series_bytes(r2_store.get_object(object_key))
    )
    assert dates == ["2026-01-15", "2026-01-16"]
    assert series["alpha_metric"] == [1.0, 2.0]
