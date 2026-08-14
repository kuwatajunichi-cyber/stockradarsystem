"""Pure snapshot assembly for Phase 4.5 derived writer."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from stockradar.metrics.canonicalize import (
    DigestRow,
    build_digest_row,
    compute_logical_digest,
)

SNAPSHOT_PARQUET_CONTENT_TYPE = "application/vnd.apache.parquet"
SNAPSHOT_JSON_FALLBACK_CONTENT_TYPE = "application/json"


def build_snapshot_rows(
    *,
    trade_date: str,
    metric_set_version_id: str,
    metric_keys_ordered: list[str],
    metric_types: dict[str, str],
    values_by_instrument: dict[str, dict[str, Any]],
) -> list[DigestRow]:
    """Build canonical digest rows from per-instrument metric values."""
    rows: list[DigestRow] = []
    for instrument_code in sorted(
        values_by_instrument,
        key=lambda code: tuple(ord(ch) for ch in str(code)),
    ):
        values = values_by_instrument[instrument_code]
        rows.append(
            build_digest_row(
                instrument_code=instrument_code,
                metric_keys_ordered=metric_keys_ordered,
                metric_types=metric_types,
                values_by_key=values,
            )
        )
    return rows


def compute_snapshot_logical_digest(
    *,
    trade_date: str,
    metric_set_version_id: str,
    rows: list[DigestRow],
) -> tuple[str, bytes]:
    return compute_logical_digest(
        trade_date=trade_date,
        metric_set_version_id=metric_set_version_id,
        rows=rows,
    )


def build_snapshot_manifest_bytes(
    *,
    trade_date: str,
    metric_set_version_id: str,
    generation_id: str,
    logical_digest: str,
    object_sha256: str,
    size_bytes: int,
    layer1_input_fingerprint: str,
    writer_workflow: str,
) -> bytes:
    payload = {
        "schema_version": 1,
        "manifest_kind": "derived_snapshot",
        "trade_date": trade_date,
        "metric_set_version_id": metric_set_version_id.strip().lower(),
        "generation_id": generation_id.strip().lower(),
        "logical_digest": logical_digest.strip().lower(),
        "object_sha256": object_sha256.strip().lower(),
        "size_bytes": int(size_bytes),
        "layer1_input_fingerprint": layer1_input_fingerprint.strip().lower(),
        "writer_workflow": writer_workflow,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_snapshot_parquet_bytes(
    *,
    trade_date: str,
    rows: list[DigestRow],
) -> bytes:
    """
    Build snapshot object bytes.

    Uses pyarrow when importable; otherwise emits deterministic JSON bytes for tests.
    """
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except ImportError:
        return _build_snapshot_json_fallback_bytes(trade_date=trade_date, rows=rows)

    table_rows: list[dict[str, Any]] = []
    for row in rows:
        values: dict[str, Any] = {}
        for atom in row["values"]:
            key = str(atom["metric_key"])
            value_type = str(atom["type"])
            raw_value = atom.get("value")
            if raw_value is None:
                values[key] = None
            elif value_type == "float":
                values[key] = float(raw_value)
            elif value_type == "int":
                values[key] = int(raw_value)
            elif value_type == "bool":
                values[key] = bool(raw_value)
            else:
                values[key] = str(raw_value)
        table_rows.append(
            {
                "trade_date": trade_date,
                "instrument_code": row["instrument_code"],
                **values,
            }
        )
    table = pa.Table.from_pylist(table_rows)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    return sink.getvalue().to_pybytes()


def _build_snapshot_json_fallback_bytes(
    *,
    trade_date: str,
    rows: list[DigestRow],
) -> bytes:
    payload = {
        "schema_version": 1,
        "format": "json_fallback",
        "trade_date": trade_date,
        "rows": rows,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compute_object_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def snapshot_content_type(content: bytes) -> str:
    if content.startswith(b"PAR1"):
        return SNAPSHOT_PARQUET_CONTENT_TYPE
    return SNAPSHOT_JSON_FALLBACK_CONTENT_TYPE
