"""Contract: Phase 4.5 pure metrics, catalogs, and golden vectors."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockradar.metrics.canonicalize import (
    build_digest_row,
    canonical_decimal_string,
    compute_logical_digest,
)
from stockradar.metrics.fingerprint import compute_definition_fingerprint, compute_set_fingerprint
from stockradar.metrics.normalize_instrument_code import normalize_instrument_code
from stockradar.metrics.perfect_order import PERFECT_ORDER_MIN_HISTORY_DAYS, compute_perfect_order_days
from stockradar.metrics.registry_spec import (
    default_metric_set_v1_free_path,
    default_metric_set_v1_path,
    load_metric_set_spec,
)

_REPO = Path(__file__).resolve().parents[1]
_GOLDEN = _REPO / "tests" / "fixtures" / "phase45_golden_vectors.json"

pytestmark = pytest.mark.unit


def _load_golden_vectors() -> dict:
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_normalize_instrument_code_golden_cases() -> None:
    data = _load_golden_vectors()
    for case in data["normalize_instrument_code_cases"]:
        assert normalize_instrument_code(case["input"]) == case["expected"]


@pytest.mark.unit
def test_canonical_decimal_golden_cases() -> None:
    data = _load_golden_vectors()
    for case in data["canonical_decimal_cases"]:
        assert canonical_decimal_string(float(case["input"])) == case["expected"]


@pytest.mark.unit
def test_logical_digest_golden_vectors_match_fixture() -> None:
    data = _load_golden_vectors()
    for item in data["logical_digest_vectors"]:
        digest, _raw = compute_logical_digest(
            trade_date=data["trade_date"],
            metric_set_version_id=data["metric_set_version_id"],
            rows=json.loads(item["utf8"])["rows"],
        )
        assert digest == item["digest"], item["name"]


@pytest.mark.unit
def test_logical_digest_golden_vectors_via_build_digest_row() -> None:
    data = _load_golden_vectors()
    for item in data["logical_digest_vectors"]:
        if item["name"] == "unicode_row_order":
            rows = [
                build_digest_row(
                    instrument_code="Ab12",
                    metric_keys_ordered=["beta_metric"],
                    metric_types={"beta_metric": "int"},
                    values_by_key={"beta_metric": 3},
                ),
                build_digest_row(
                    instrument_code="0001",
                    metric_keys_ordered=["beta_metric"],
                    metric_types={"beta_metric": "int"},
                    values_by_key={"beta_metric": 1},
                ),
            ]
        elif item["name"] == "neg_zero_float":
            rows = [
                build_digest_row(
                    instrument_code="0001",
                    metric_keys_ordered=["alpha_metric"],
                    metric_types={"alpha_metric": "float"},
                    values_by_key={"alpha_metric": -0.0},
                )
            ]
        else:
            continue
        digest, _ = compute_logical_digest(
            trade_date=data["trade_date"],
            metric_set_version_id=data["metric_set_version_id"],
            rows=rows,
        )
        assert digest == item["digest"], item["name"]


@pytest.mark.unit
def test_int_metric_invalid_string_becomes_missing() -> None:
    row = build_digest_row(
        instrument_code="0001",
        metric_keys_ordered=["beta_metric"],
        metric_types={"beta_metric": "int"},
        values_by_key={"beta_metric": "abc"},
    )
    assert row["values"][0]["value"] is None
    assert "beta_metric" in row["flags"]["missing_metrics"]


@pytest.mark.unit
def test_yaml_definition_fingerprints_match_canonical() -> None:
    for path in (default_metric_set_v1_path(), default_metric_set_v1_free_path()):
        spec = load_metric_set_spec(path)
        for member in spec.members:
            expected = compute_definition_fingerprint(member.definition_canonical)
            assert member.definition_fingerprint == expected, member.metric_key
    full = load_metric_set_spec(default_metric_set_v1_path())
    free = load_metric_set_spec(default_metric_set_v1_free_path())
    assert len(full.members) == 21
    assert len(free.members) == 13
    assert full.set_family == "daily_core_v1"
    assert free.set_family == "daily_core_v1"


@pytest.mark.unit
def test_fingerprint_is_deterministic() -> None:
    definition = {
        "metric_key": "alpha_metric",
        "value_type": "float",
        "parameters": {"window": 25},
    }
    first = compute_definition_fingerprint(definition)
    second = compute_definition_fingerprint(dict(definition))
    assert first == second
    assert len(first) == 64

    members = [
        {"metric_key": "alpha_metric", "definition_fingerprint": first, "ordinal": 0},
        {"metric_key": "beta_metric", "definition_fingerprint": first, "ordinal": 1},
    ]
    set_a = compute_set_fingerprint(members=members, set_family="v1")
    set_b = compute_set_fingerprint(members=list(members), set_family="v1")
    assert set_a == set_b


@pytest.mark.unit
def test_perfect_order_uptrend_counts_consecutive_days() -> None:
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    close = pd.Series([50 + i for i in range(300)], index=dates)
    run_date = dates[-1].date()
    result = compute_perfect_order_days(close=close, run_date=run_date)
    assert isinstance(result, int)
    assert result > 0


@pytest.mark.unit
def test_perfect_order_flat_series_returns_zero() -> None:
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    close = pd.Series([100.0] * 300, index=dates)
    run_date = dates[-1].date()
    assert compute_perfect_order_days(close=close, run_date=run_date) == 0


@pytest.mark.unit
def test_perfect_order_insufficient_history_returns_none() -> None:
    dates = pd.date_range("2024-01-01", periods=PERFECT_ORDER_MIN_HISTORY_DAYS - 1, freq="B")
    close = pd.Series([100.0 + i for i in range(len(dates))], index=dates)
    run_date = dates[-1].date()
    assert compute_perfect_order_days(close=close, run_date=run_date) is None


@pytest.mark.unit
def test_perfect_order_missing_run_date_bar_returns_none() -> None:
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    close = pd.Series([50 + i for i in range(300)], index=dates)
    assert compute_perfect_order_days(close=close, run_date=date(2099, 12, 31)) is None
