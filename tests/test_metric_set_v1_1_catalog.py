"""Catalog draft for metric_set_v1_1 (sma75 RS). Does not switch active v1."""

from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.metrics.registry_spec import load_metric_set_spec
from stockradar.metrics.seed_catalog import SET_KEY_PATTERN

_REPO = Path(__file__).resolve().parents[1]
_V11 = _REPO / "config" / "metrics" / "metric_set_v1_1.yaml"
_V11_FREE = _REPO / "config" / "metrics" / "metric_set_v1_1_free.yaml"
_V1 = _REPO / "config" / "metrics" / "metric_set_v1.yaml"
_V1_FREE = _REPO / "config" / "metrics" / "metric_set_v1_free.yaml"

pytestmark = pytest.mark.unit


def test_v1_unchanged_member_counts() -> None:
    assert len(load_metric_set_spec(_V1).members) == 21
    assert len(load_metric_set_spec(_V1_FREE).members) == 13
    assert "rs_sma75_topix" not in load_metric_set_spec(_V1).metric_keys_ordered


def test_v1_1_adds_sma75_on_both_benches() -> None:
    full = load_metric_set_spec(_V11)
    free = load_metric_set_spec(_V11_FREE)
    assert full.set_family == "daily_core_v1_1"
    assert free.set_family == "daily_core_v1_1"
    assert len(full.members) == 23
    assert len(free.members) == 15
    for spec in (full, free):
        keys = spec.metric_keys_ordered
        assert "rs_sma75_topix" in keys
        assert "rs_sma75_nikkei" in keys
        topix = next(m for m in spec.members if m.metric_key == "rs_sma75_topix")
        assert topix.parameters == {"sma_window": 75, "rs_window": 31}
        assert topix.min_history_days == 105
        assert topix.required_benchmarks == ("TOPIX",)
        nikkei = next(m for m in spec.members if m.metric_key == "rs_sma75_nikkei")
        assert nikkei.required_benchmarks == ("N225",)
    assert SET_KEY_PATTERN.match(full.set_key)
    assert SET_KEY_PATTERN.match(free.set_key)
