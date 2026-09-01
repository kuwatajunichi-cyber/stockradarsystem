"""Roundtrip: ADR-005 series_seed write via Fake generation + R2 stores."""
from __future__ import annotations

import gzip
import json

import pytest

from stockradar.jobs.write_series_only_generation import (
    ExistingSeriesState,
    build_series_seed_delta_bytes,
    load_existing_series_state,
    plan_series_only_trade_date,
    run_series_only_trade_date,
    series_seed_delta_object_key,
)
from stockradar.storage.derived_generation import FakeMetricGenerationStore
from stockradar.storage.derived_series import (
    gunzip_series_bytes,
    parse_series_canonical_bytes,
)
from stockradar.storage.r2_object_store import FakeR2ObjectStore

pytestmark = pytest.mark.unit

SET_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
REQUEST_ID = "mnc-v1-" + ("a" * 64)
METRIC_KEYS = ["rs31_topix", "price_change_pct"]
FINGERPRINT = "b" * 64


def test_series_seed_delta_bytes_sorted_and_gzipped() -> None:
    content = build_series_seed_delta_bytes(
        request_id=REQUEST_ID,
        trade_date="2026-01-15",
        metric_set_version_id=SET_ID,
        generation_id="11111111-2222-3333-4444-555555555555",
        object_kind="series_seed_delta",
        rows=[
            {"instrument_code": "7203", "metric_key": "rs31_topix", "value": 1.0, "flags": []},
            {"instrument_code": "1301", "metric_key": "price_change_pct", "value": None, "flags": []},
            {"instrument_code": "1301", "metric_key": "rs31_topix", "value": 0.5, "flags": []},
        ],
    )
    payload = json.loads(gzip.decompress(content).decode("utf-8"))
    assert payload["schema_version"] == 1
    assert payload["object_kind"] == "series_seed_delta"
    codes_keys = [(r["instrument_code"], r["metric_key"]) for r in payload["rows"]]
    assert codes_keys == sorted(codes_keys)
    assert codes_keys[0] == ("1301", "price_change_pct")


def test_run_series_only_trade_date_roundtrip_prior_absent() -> None:
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    plan = plan_series_only_trade_date(
        request_id=REQUEST_ID,
        mode="series_seed",
        trade_date="2026-01-15",
        candidate_codes=["1301"],
        existing_dates_by_code={},
    )
    assert plan.expected_object_count == 3
    generation_id = run_series_only_trade_date(
        plan=plan,
        metric_set_version_id=SET_ID,
        github_run_id=42,
        values_by_code={"1301": {"rs31_topix": 1.25, "price_change_pct": -0.5}},
        existing_state=ExistingSeriesState(),
        generation_store=generation_store,
        r2_store=r2_store,
        metric_keys_ordered=METRIC_KEYS,
        set_fingerprint=FINGERPRINT,
    )
    assert generation_id is not None

    object_key = generation_store.get_committed_series_object_key(
        metric_set_version_id=SET_ID,
        instrument_code="1301",
        series_year=2026,
    )
    assert object_key is not None
    dates, series, _flags = parse_series_canonical_bytes(
        gunzip_series_bytes(r2_store.get_object(object_key))
    )
    assert dates == ["2026-01-15"]
    assert series["rs31_topix"] == [1.25]
    assert series["price_change_pct"] == [-0.5]

    pending = generation_store.list_pending_objects(generation_id)
    kinds = {row.object_kind for row in pending}
    assert kinds == {"series", "series_manifest", "series_seed_delta"}
    delta_row = next(row for row in pending if row.object_kind == "series_seed_delta")
    assert delta_row.object_key == series_seed_delta_object_key(
        request_id=REQUEST_ID,
        trade_date="2026-01-15",
        generation_id=generation_id,
        sha256=delta_row.byte_sha256,
    )
    delta_payload = json.loads(
        gunzip_series_bytes(r2_store.get_object(delta_row.object_key)).decode("utf-8")
    )
    assert delta_payload["object_kind"] == "series_seed_delta"
    assert len(delta_payload["rows"]) == 2

    reloaded = load_existing_series_state(
        generation_store,
        r2_store,
        SET_ID,
        ["1301"],
        2026,
    )
    assert reloaded.dates_by_code["1301"] == ["2026-01-15"]
    assert "1301" in reloaded.prior_digest_by_code


def test_run_series_only_trade_date_skips_when_noop() -> None:
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    plan = plan_series_only_trade_date(
        request_id=REQUEST_ID,
        mode="series_seed",
        trade_date="2026-01-15",
        candidate_codes=["1301"],
        existing_dates_by_code={"1301": ["2026-01-15"]},
    )
    assert plan.expected_object_count == 0
    assert (
        run_series_only_trade_date(
            plan=plan,
            metric_set_version_id=SET_ID,
            github_run_id=1,
            values_by_code={},
            generation_store=generation_store,
            r2_store=r2_store,
            metric_keys_ordered=METRIC_KEYS,
            set_fingerprint=FINGERPRINT,
        )
        is None
    )
    assert generation_store.generations == {}
