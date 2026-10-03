"""Contract tests for derived-web-asof bundle JSON."""
from __future__ import annotations

import copy

import pytest

from stockradar.storage.web_asof_bundle import (
    AXIS_LEN,
    SCHEMA_ID,
    SMA75_NON_NULL_RATE_MIN,
    gzip_bundle_bytes,
    gunzip_bundle_bytes,
    object_key,
    sma75_cas_allowed,
    validate_web_asof_bundle,
    WebAsofBundleError,
)

pytestmark = pytest.mark.unit

_FP = "a" * 64
_SET = "11111111-2222-3333-4444-555555555555"


def _valid() -> dict:
    axis = [f"2026-06-{i:02d}" for i in range(1, 31)] + [
        f"2026-07-{i:02d}" for i in range(1, 31)
    ]
    axis = axis[:AXIS_LEN]
    axis[-1] = "2026-07-30"
    zeros = [0.1] * AXIS_LEN
    row = {
        "code": "7203",
        "name": "Toyota",
        "z_turnover_60": 0.1,
        "rs_acceleration": 0.1,
        "rs_acceleration_zscore": 0.1,
        "rs31": 0.1,
        "rs63": 0.1,
        "rs126": 0.1,
        "rs252": 0.1,
        "rs_sma75": 0.1,
    }
    series_one = {
        "z_turnover_60": list(zeros),
        "rs_acceleration": list(zeros),
        "rs_acceleration_zscore": list(zeros),
        "rs31": list(zeros),
        "rs63": list(zeros),
        "rs126": list(zeros),
        "rs252": list(zeros),
        "rs_sma75": list(zeros),
    }
    return {
        "schema_id": SCHEMA_ID,
        "as_of": "2026-07-30",
        "benchmark": "topix",
        "metric_set_version_id": _SET,
        "set_fingerprint": _FP,
        "axis_dates": axis,
        "rows": [row],
        "series": {"7203": series_one},
    }


def test_valid_bundle_and_gzip_roundtrip() -> None:
    payload = _valid()
    validate_web_asof_bundle(payload)
    blob = gzip_bundle_bytes(payload)
    assert len(blob) < 8 * 1024 * 1024
    again = gunzip_bundle_bytes(blob)
    validate_web_asof_bundle(again)


def test_object_key_is_per_bench() -> None:
    k = object_key(
        metric_set_version_id=_SET,
        benchmark="TOPIX",
        as_of="2026-07-30",
    )
    assert k.startswith("derived-web-asof/")
    assert "benchmark=topix" in k
    assert "as-of=2026-07-30" in k
    assert k.endswith("bundle.json.gz")


def test_duplicate_code_rejected() -> None:
    payload = _valid()
    payload["rows"].append(copy.deepcopy(payload["rows"][0]))
    payload["series"]["7203"] = payload["series"]["7203"]
    with pytest.raises(WebAsofBundleError, match="unique"):
        validate_web_asof_bundle(payload)


def test_axis_length_mismatch_rejected() -> None:
    payload = _valid()
    payload["series"]["7203"]["rs31"] = payload["series"]["7203"]["rs31"][:-1]
    with pytest.raises(WebAsofBundleError, match="length"):
        validate_web_asof_bundle(payload)


def test_missing_sma75_column_rejected() -> None:
    payload = _valid()
    del payload["rows"][0]["rs_sma75"]
    with pytest.raises(WebAsofBundleError, match="rs_sma75"):
        validate_web_asof_bundle(payload)


def test_sma75_cas_rejects_empty_and_all_null() -> None:
    assert SMA75_NON_NULL_RATE_MIN == 0.98
    assert sma75_cas_allowed([0.1] * 100)
    assert not sma75_cas_allowed([])
    assert not sma75_cas_allowed([None] * 100)
    almost = [0.1] * 97 + [None] * 3
    assert not sma75_cas_allowed(almost)
    ok = [0.1] * 98 + [None] * 2
    assert sma75_cas_allowed(ok)
    ineligible_nulls = [0.1] * 98 + [None] * 5
    mask = [True] * 98 + [False] * 5
    assert sma75_cas_allowed(ineligible_nulls, eligible=mask)
    assert not sma75_cas_allowed(ineligible_nulls)
    with pytest.raises(ValueError, match="eligible mask"):
        sma75_cas_allowed([0.1], eligible=[True, False])


def test_alphanumeric_jpx_code_accepted() -> None:
    payload = _valid()
    payload["rows"][0]["code"] = "135A"
    payload["series"]["135A"] = payload["series"].pop("7203")
    validate_web_asof_bundle(payload)


def test_optional_last_bar_metrics_accepted() -> None:
    payload = _valid()
    payload["rows"][0]["turnover_ma_ratio_60"] = 1.5
    payload["rows"][0]["price_change_pct"] = -0.2
    payload["rows"][0]["perfect_order_days"] = 4
    payload["rows"][0]["beta_adjusted_rs"] = 0.3
    payload["rows"][0]["information_ratio"] = 0.4
    validate_web_asof_bundle(payload)


def test_schema_lists_optional_last_bar_keys() -> None:
    from pathlib import Path

    schema = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "contracts"
        / "web_asof_bundle.schema.json"
    ).read_text(encoding="utf-8")
    for key in (
        "turnover_ma_ratio_60",
        "price_change_pct",
        "perfect_order_days",
        "beta_adjusted_rs",
        "information_ratio",
    ):
        assert key in schema
