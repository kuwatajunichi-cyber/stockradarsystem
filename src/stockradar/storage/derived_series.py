"""Pure series assembly for Phase 4.5 derived writer."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from typing import Any

from stockradar.storage.derived_snapshot import (
    DERIVED_WRITER_VERSION,
    coerce_row_flags,
    dump_canonical_json,
    empty_row_flags,
    flags_for_values,
)

SERIES_GZIP_CONTENT_TYPE = "application/gzip"

SERIES_MANIFEST_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "generation_id",
    "metric_set_version_id",
    "set_fingerprint",
    "instrument_code",
    "year",
    "logical_digest",
    "object_sha256",
    "object_size",
    "source_github_run_id",
    "row_count",
    "metric_keys_ordered",
    "mode",
    "writer_workflow",
    "writer_version",
    "serialization",
)

SERIES_SERIALIZATION: dict[str, Any] = {
    "format": "json",
    "gzip": {"mtime": 0, "compresslevel": 9, "filename": ""},
}


def build_series_canonical_payload(
    *,
    instrument_code: str,
    year: int,
    dates: list[str],
    series: dict[str, list[Any]],
    flags: list[dict[str, Any]],
    metric_keys_ordered: list[str],
) -> dict[str, Any]:
    """Build series canonical JSON payload (fixed key order per phase45_canonical_digest.md)."""
    ordered_series = {key: list(series[key]) for key in metric_keys_ordered}
    canonical_flags = [coerce_row_flags(item) for item in flags]
    return {
        "schema_version": 1,
        "instrument_code": instrument_code,
        "year": int(year),
        "dates": list(dates),
        "series": ordered_series,
        "flags": canonical_flags,
    }


def build_series_canonical_bytes(
    *,
    instrument_code: str,
    year: int,
    dates: list[str],
    series: dict[str, list[Any]],
    flags: list[dict[str, Any]],
    metric_keys_ordered: list[str],
) -> bytes:
    payload = build_series_canonical_payload(
        instrument_code=instrument_code,
        year=year,
        dates=dates,
        series=series,
        flags=flags,
        metric_keys_ordered=metric_keys_ordered,
    )
    return dump_canonical_json(payload)


def gzip_series_bytes(content: bytes) -> bytes:
    """Gzip canonical series bytes with mtime=0 for deterministic object hash."""
    buffer = io.BytesIO()
    with gzip.GzipFile(
        fileobj=buffer,
        mode="wb",
        compresslevel=9,
        mtime=0,
    ) as gz:
        gz.write(content)
    return buffer.getvalue()


def build_series_manifest_bytes(
    *,
    instrument_code: str,
    year: int,
    metric_set_version_id: str,
    generation_id: str,
    logical_digest: str,
    object_sha256: str,
    object_size: int,
    writer_workflow: str,
    set_fingerprint: str,
    source_github_run_id: int,
    row_count: int,
    metric_keys_ordered: list[str],
    mode: str,
    writer_version: str = DERIVED_WRITER_VERSION,
    serialization: dict[str, Any] | None = None,
) -> bytes:
    payload = {
        "schema_version": 1,
        "generation_id": generation_id.strip().lower(),
        "metric_set_version_id": metric_set_version_id.strip().lower(),
        "set_fingerprint": set_fingerprint.strip().lower(),
        "instrument_code": instrument_code,
        "year": int(year),
        "logical_digest": logical_digest.strip().lower(),
        "object_sha256": object_sha256.strip().lower(),
        "object_size": int(object_size),
        "source_github_run_id": int(source_github_run_id),
        "row_count": int(row_count),
        "metric_keys_ordered": list(metric_keys_ordered),
        "mode": str(mode).strip().lower(),
        "writer_workflow": writer_workflow,
        "writer_version": writer_version,
        "serialization": dict(serialization or SERIES_SERIALIZATION),
    }
    ordered = {key: payload[key] for key in SERIES_MANIFEST_FIELD_ORDER}
    return dump_canonical_json(ordered)


def compute_object_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def gunzip_series_bytes(content: bytes) -> bytes:
    """Decompress gzip series object bytes to canonical JSON bytes."""
    return gzip.decompress(content)


def parse_series_canonical_bytes(
    content: bytes,
) -> tuple[list[str], dict[str, list[Any]], list[dict[str, Any]]]:
    payload = json.loads(content.decode("utf-8"))
    dates = [str(item) for item in payload["dates"]]
    series = {str(key): list(value) for key, value in payload["series"].items()}
    flags = [coerce_row_flags(item) for item in payload["flags"]]
    return dates, series, flags


def merge_trade_date_into_series(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values: dict[str, Any],
    metric_types: dict[str, str] | None = None,
    instrument_code: str = "0000",
    prior_dates: list[str] | None = None,
    prior_series: dict[str, list[Any]] | None = None,
    prior_flags: list[dict[str, Any]] | None = None,
) -> tuple[list[str], dict[str, list[Any]], list[dict[str, Any]]]:
    """Merge one trade_date observation into an existing year series (or start new)."""
    types = metric_types or {key: "float" for key in metric_keys_ordered}
    new_flags = flags_for_values(
        instrument_code=instrument_code,
        metric_keys_ordered=metric_keys_ordered,
        metric_types=types,
        values_by_key=values,
    )
    if not prior_dates:
        dates = [trade_date]
        series = {key: [values.get(key)] for key in metric_keys_ordered}
        return dates, series, [new_flags]

    dates = list(prior_dates)
    flags = [coerce_row_flags(item) for item in (prior_flags or [empty_row_flags() for _ in prior_dates])]
    if trade_date in dates:
        idx = dates.index(trade_date)
        series: dict[str, list[Any]] = {}
        for key in metric_keys_ordered:
            prior_vals = list((prior_series or {}).get(key, []))
            while len(prior_vals) <= idx:
                prior_vals.append(None)
            prior_vals[idx] = values.get(key)
            series[key] = prior_vals
        while len(flags) <= idx:
            flags.append(empty_row_flags())
        flags[idx] = new_flags
        return dates, series, flags

    dates = prior_dates + [trade_date]
    series = {}
    for key in metric_keys_ordered:
        prior_vals = list((prior_series or {}).get(key, []))
        series[key] = prior_vals + [values.get(key)]
    flags = flags + [new_flags]
    return dates, series, flags
