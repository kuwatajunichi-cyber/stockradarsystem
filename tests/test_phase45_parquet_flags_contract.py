"""Contract: snapshot parquet _flags is a struct/object, not a JSON string."""
from __future__ import annotations

import io

import pytest

from stockradar.storage.derived_snapshot import (
    LATEST_FLAGS_KEY,
    build_snapshot_parquet_bytes,
    build_snapshot_rows,
)

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"


def test_snapshot_parquet_flags_are_object_not_json_string() -> None:
    rows = build_snapshot_rows(
        trade_date="2026-01-15",
        metric_set_version_id=SET_ID,
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument={"1301": {"alpha_metric": 1.0}},
    )
    content = build_snapshot_parquet_bytes(trade_date="2026-01-15", rows=rows)
    if content.startswith(b"PAR1"):
        import pyarrow.parquet as pq

        table = pq.read_table(io.BytesIO(content))
        flags = table.column(LATEST_FLAGS_KEY)[0].as_py()
        assert isinstance(flags, dict)
        assert not isinstance(flags, str)
        assert flags["missing_metrics"] == []
        assert flags["non_finite_metrics"] == []
        assert flags["po_indeterminate"] is False
        return
    payload = __import__("json").loads(content.decode("utf-8"))
    flags = payload["rows"][0]["flags"]
    assert isinstance(flags, dict)
    assert flags["missing_metrics"] == []
