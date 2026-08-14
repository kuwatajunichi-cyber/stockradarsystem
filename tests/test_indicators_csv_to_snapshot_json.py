"""Contract: indicators CSV to snapshot JSON requires catalog columns."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from stockradar.metrics.registry_spec import default_metric_set_v1_free_path, load_metric_set_spec

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_CONVERTER = _REPO / "scripts" / "storage" / "indicators_csv_to_snapshot_json.py"


def _load_converter():
    spec = importlib.util.spec_from_file_location("indicators_csv_to_snapshot_json", _CONVERTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_converter_requires_catalog_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "indicators.csv"
    pd.DataFrame({"code": ["7200"], "z_turnover_60": [0.1]}).to_csv(csv_path, index=False)
    converter = _load_converter()
    with pytest.raises(ValueError, match="missing catalog columns"):
        converter.indicators_csv_to_snapshot(csv_path, default_metric_set_v1_free_path())


def test_converter_maps_catalog_columns(tmp_path: Path) -> None:
    yaml_path = default_metric_set_v1_free_path()
    spec = load_metric_set_spec(yaml_path)
    row: dict[str, object] = {"code": "7200"}
    for member in spec.members:
        row[member.metric_key] = 1 if member.value_type == "int" else 1.0
    csv_path = tmp_path / "indicators.csv"
    pd.DataFrame([row]).to_csv(csv_path, index=False)
    snapshot = _load_converter().indicators_csv_to_snapshot(csv_path, yaml_path)
    assert "7200" in snapshot
    assert "perfect_order_days" in snapshot["7200"]
    assert snapshot["7200"]["perfect_order_days"] == 1
