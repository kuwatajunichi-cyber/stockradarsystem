"""Pure series assembly for Phase 4.5 derived writer."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from typing import Any

SERIES_GZIP_CONTENT_TYPE = "application/gzip"


def build_series_canonical_payload(
    *,
    instrument_code: str,
    year: int,
    dates: list[str],
    series: dict[str, list[Any]],
    flags: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build series canonical JSON payload (fixed key order per phase45_canonical_digest.md)."""
    ordered_series = {key: list(series[key]) for key in sorted(series)}
    return {
        "schema_version": 1,
        "instrument_code": instrument_code,
        "year": int(year),
        "dates": list(dates),
        "series": ordered_series,
        "flags": list(flags),
    }


def build_series_canonical_bytes(
    *,
    instrument_code: str,
    year: int,
    dates: list[str],
    series: dict[str, list[Any]],
    flags: list[dict[str, Any]],
) -> bytes:
    payload = build_series_canonical_payload(
        instrument_code=instrument_code,
        year=year,
        dates=dates,
        series=series,
        flags=flags,
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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
    size_bytes: int,
    writer_workflow: str,
) -> bytes:
    payload = {
        "schema_version": 1,
        "manifest_kind": "derived_series",
        "instrument_code": instrument_code,
        "year": int(year),
        "metric_set_version_id": metric_set_version_id.strip().lower(),
        "generation_id": generation_id.strip().lower(),
        "logical_digest": logical_digest.strip().lower(),
        "object_sha256": object_sha256.strip().lower(),
        "size_bytes": int(size_bytes),
        "writer_workflow": writer_workflow,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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
    flags = [dict(item) for item in payload["flags"]]
    return dates, series, flags


def merge_trade_date_into_series(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values: dict[str, Any],
    prior_dates: list[str] | None = None,
    prior_series: dict[str, list[Any]] | None = None,
    prior_flags: list[dict[str, Any]] | None = None,
) -> tuple[list[str], dict[str, list[Any]], list[dict[str, Any]]]:
    """Merge one trade_date observation into an existing year series (or start new)."""
    if not prior_dates:
        dates = [trade_date]
        series = {key: [values.get(key)] for key in metric_keys_ordered}
        return dates, series, [{}]

    dates = list(prior_dates)
    flags = list(prior_flags or [{} for _ in prior_dates])
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
            flags.append({})
        return dates, series, flags

    dates = prior_dates + [trade_date]
    series = {}
    for key in metric_keys_ordered:
        prior_vals = list((prior_series or {}).get(key, []))
        series[key] = prior_vals + [values.get(key)]
    flags = flags + [{}]
    return dates, series, flags
