"""Assemble Track D web_asof_bundle_v1 payloads from freeze SQLite.

Live daily stays mapping-gated. This module does not CAS metric_set_v1_1.
"""
from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from stockradar.jobs.write_web_asof_bundle import (
    build_web_asof_bundle_payload,
    project_csv_row,
    window_series_to_axis,
)
from stockradar.storage.web_asof_bundle import AXIS_LEN, BENCHMARKS, sma75_cas_allowed


class AssembleWebAsofError(RuntimeError):
    pass


def payloads_from_freeze_sqlite(
    sqlite_path: Path,
    *,
    metric_set_version_id: str,
    set_fingerprint: str,
) -> dict[str, dict[str, Any]]:
    """Project a freeze SQLite snapshot into topix/nikkei bundle payloads."""
    if not sqlite_path.is_file():
        raise AssembleWebAsofError(f"freeze sqlite missing: {sqlite_path}")
    conn = sqlite3.connect(str(sqlite_path))
    try:
        meta = conn.execute(
            "SELECT as_of, axis_dates_json, n_rows FROM meta LIMIT 1"
        ).fetchone()
        if meta is None:
            raise AssembleWebAsofError("freeze sqlite has no meta row")
        as_of = str(meta[0]).strip()
        axis_dates = json.loads(str(meta[1]))
        n_rows = int(meta[2])
        if not isinstance(axis_dates, list) or len(axis_dates) != AXIS_LEN:
            raise AssembleWebAsofError(f"axis_dates must have length {AXIS_LEN}")
        if axis_dates[-1] != as_of:
            raise AssembleWebAsofError("axis last date must equal as_of")
        if n_rows < 1:
            raise AssembleWebAsofError("freeze sqlite has zero rows")

        row_map: dict[str, dict[str, Any]] = {}
        for code, payload_json in conn.execute("SELECT code, payload_json FROM rows"):
            payload = json.loads(str(payload_json))
            if not isinstance(payload, dict):
                raise AssembleWebAsofError(f"row {code}: payload_json must be an object")
            row_map[str(code).zfill(4)] = payload

        series_map: dict[str, dict[str, Any]] = {}
        for code, metrics_json in conn.execute("SELECT code, metrics_json FROM series"):
            blob = json.loads(str(metrics_json))
            if not isinstance(blob, dict) or not isinstance(blob.get("values"), dict):
                raise AssembleWebAsofError(f"series {code}: metrics_json.values required")
            series_map[str(code).zfill(4)] = blob["values"]
    finally:
        conn.close()

    if set(row_map) != set(series_map):
        raise AssembleWebAsofError("freeze sqlite row codes must equal series codes")

    out: dict[str, dict[str, Any]] = {}
    for bench in ("topix", "nikkei"):
        if bench not in BENCHMARKS:
            continue
        projected_rows: list[dict[str, Any]] = []
        projected_series: dict[str, dict[str, list[Any]]] = {}
        sma_values: list[Any] = []
        for code in sorted(row_map):
            csv_row = dict(row_map[code])
            csv_row.setdefault("date", as_of)
            row = project_csv_row(csv_row, bench=bench, as_of=as_of)
            series = window_series_to_axis(
                list(axis_dates),
                series_map[code],
                list(axis_dates),
                bench=bench,
            )
            projected_rows.append(row)
            projected_series[code] = series
            sma_values.append(row.get("rs_sma75"))
        # Fail-closed: no 105-day eligibility mask on freeze rows, so every
        # name is in the denominator (short-history nulls cannot inflate 0.98).
        if not sma75_cas_allowed(sma_values):
            raise AssembleWebAsofError(
                f"{bench} rs_sma75 non-null rate below SMA75_NON_NULL_RATE_MIN"
            )
        out[bench] = build_web_asof_bundle_payload(
            as_of=as_of,
            benchmark=bench,
            metric_set_version_id=metric_set_version_id,
            set_fingerprint=set_fingerprint,
            axis_dates=list(axis_dates),
            rows=projected_rows,
            series=projected_series,
        )
    return out


def write_payload_files(
    payloads: Mapping[str, Mapping[str, Any]],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for bench, payload in payloads.items():
        path = out_dir / f"bundle_{bench}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        paths[bench] = path
    return paths


def write_universe_csv_from_ohlc_zip(zip_path: Path, as_of: str, dest: Path) -> int:
    """Minimal date,code,name CSV from OHLC zip members.

    Used when R2 staging has expired the enriched CSV (r2_runs_staging_days=14).
    Freeze recomputes last-bar metrics from the cache; news/identity stay empty.
    """
    date.fromisoformat(as_of)
    if not zip_path.is_file():
        raise AssembleWebAsofError(f"ohlc zip missing: {zip_path}")
    codes: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            stem = Path(name).stem.strip()
            if len(stem) != 4 or not stem.isalnum():
                continue
            codes.append(stem.zfill(4) if stem.isdigit() else stem)
    unique = sorted(set(codes))
    if not unique:
        raise AssembleWebAsofError(f"ohlc zip has no ticker csvs: {zip_path}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,code,name\n"]
    lines.extend(f"{as_of},{code},\n" for code in unique)
    dest.write_text("".join(lines), encoding="utf-8")
    return len(unique)


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    if not zip_path.is_file():
        raise AssembleWebAsofError(f"zip missing: {zip_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
