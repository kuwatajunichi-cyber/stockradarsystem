"""Freeze as-of cross-section + shared-axis series into SQLite (read-only inputs)."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from stockradar.indicators.date_anchor import (
    build_anchor_context,
    merged_close,
    prepare_asof_series,
)
from stockradar.indicators.rs import (
    compute_rs_acceleration_from_merged,
    compute_rs_acceleration_zscore_from_merged,
    compute_rs_from_merged,
)
from stockradar.indicators.zscore import compute_zscore_turnover_from_prepared
from stockradar.prototype_web_ui_asof import ABS_TOL, AXIS_LEN
from stockradar.prototype_web_ui_asof.axis import require_index_asof_bar, xtks_axis_dates
from stockradar.prototype_web_ui_asof.sma75_rs import sma_series
from stockradar.utils.candle_descriptor import compute_candle_descriptors

RS_WINDOWS = (31, 63, 126, 252)
BENCHES = ("topix", "nikkei")

# Keys always overwritten from cache-computed last bar (CSV keeps identity/links/news).
COMPUTED_ROW_KEYS = (
    "z_turnover_60",
    *(f"rs{w}_{b}" for b in BENCHES for w in RS_WINDOWS),
    *(f"rs_acceleration_{b}" for b in BENCHES),
    *(f"rs_acceleration_zscore_{b}" for b in BENCHES),
    *(f"rs_sma75_{b}" for b in BENCHES),
)


@dataclass(frozen=True)
class FreezePaths:
    csv_path: Path
    daily_cache_dir: Path
    index_cache_dir: Path
    out_sqlite: Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_session_calendar_index(index_like: pd.Index) -> pd.DatetimeIndex:
    """Map OHLC timestamps to XTKS session calendar dates (Asia/Tokyo).

    JP daily bars are often ``YYYY-MM-DD 00:00:00+09:00``. Converting those
    to UTC-naive shifts the calendar date back one day, so every Friday on an
    XTKS axis becomes an empty hole (line "valleys" on the chart). Keep Tokyo
    session dates so the shared trading-day axis lines up with bars.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(index_like))
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Tokyo").tz_localize(None)
    return idx.normalize()


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = _to_session_calendar_index(out.index)
    out = out.sort_index()
    return out[~out.index.duplicated(keep="last")]


def load_index_close(path: Path) -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = _normalize_ohlc(df)
    if "Close" not in df.columns:
        raise ValueError(f"index cache missing Close: {path}")
    return df["Close"].astype(float)


def load_stock_ohlc(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = _normalize_ohlc(df)
    for col in ("Close", "Volume"):
        if col not in df.columns:
            raise ValueError(f"stock cache missing {col}: {path}")
    return df


def index_session_dates(close: pd.Series) -> set[date]:
    return {ts.date() for ts in close.index}


def _json_sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return _json_sanitize(obj.item())
        except Exception:
            return str(obj)
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return obj


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def _empty_metric_row() -> dict[str, float | None]:
    row: dict[str, float | None] = {"z_turnover_60": None}
    for b in BENCHES:
        row[f"rs_sma75_{b}"] = None
        row[f"rs_acceleration_{b}"] = None
        row[f"rs_acceleration_zscore_{b}"] = None
        for w in RS_WINDOWS:
            row[f"rs{w}_{b}"] = None
    return row


def _metrics_for_symbol(
    stock_df: pd.DataFrame,
    benches: dict[str, pd.Series],
    axis: list[date],
) -> list[dict[str, float | None]]:
    stock_dates = {ts.date() for ts in stock_df.index}
    stock_close = stock_df["Close"]
    z_ctx = build_anchor_context(stock_df.index)

    prepared: dict[str, dict[str, Any]] = {}
    sma_prepared: dict[str, Any] = {}
    for b_name, bench_close in benches.items():
        merged = merged_close(
            pd.DataFrame({"Close": stock_close}),
            pd.DataFrame({"Close": bench_close}),
        )
        ctx = build_anchor_context(merged.index)
        prepared[b_name] = {
            "merged": merged,
            "ctx": ctx,
            "stock_asof": prepare_asof_series(merged["stock_close"]),
            "bench_asof": prepare_asof_series(merged["bench_close"]),
        }
        stock_sma = sma_series(stock_close, 75).dropna()
        bench_sma = sma_series(bench_close, 75).dropna()
        if stock_sma.empty or bench_sma.empty:
            sma_prepared[b_name] = None
        else:
            sma_merged = merged_close(
                pd.DataFrame({"Close": stock_sma}),
                pd.DataFrame({"Close": bench_sma}),
            )
            sma_prepared[b_name] = {
                "merged": sma_merged,
                "ctx": build_anchor_context(sma_merged.index),
                "stock_asof": prepare_asof_series(sma_merged["stock_close"]),
                "bench_asof": prepare_asof_series(sma_merged["bench_close"]),
            }

    out: list[dict[str, float | None]] = []
    for day in axis:
        if day not in stock_dates:
            out.append(_empty_metric_row())
            continue
        row = _empty_metric_row()
        z = compute_zscore_turnover_from_prepared(stock_df, 60, day, anchor_ctx=z_ctx)
        row["z_turnover_60"] = _f(z.iloc[0] if not z.empty else None)
        for b_name in BENCHES:
            prep = prepared[b_name]
            rs_df = compute_rs_from_merged(
                prep["merged"],
                list(RS_WINDOWS),
                day,
                anchor_ctx=prep["ctx"],
                stock_asof=prep["stock_asof"],
                bench_asof=prep["bench_asof"],
            )
            for w in RS_WINDOWS:
                row[f"rs{w}_{b_name}"] = None if rs_df.empty else _f(rs_df.iloc[0].get(f"rs{w}"))
            acc = compute_rs_acceleration_from_merged(
                prep["merged"],
                day,
                anchor_ctx=prep["ctx"],
                stock_asof=prep["stock_asof"],
                bench_asof=prep["bench_asof"],
            )
            row[f"rs_acceleration_{b_name}"] = _f(acc.iloc[0] if not acc.empty else None)
            acc_z = compute_rs_acceleration_zscore_from_merged(
                prep["merged"],
                day,
                lookback_days=60,
                anchor_ctx=prep["ctx"],
                stock_asof=prep["stock_asof"],
                bench_asof=prep["bench_asof"],
            )
            row[f"rs_acceleration_zscore_{b_name}"] = _f(acc_z.iloc[0] if not acc_z.empty else None)
            sma_prep = sma_prepared[b_name]
            if sma_prep is None:
                row[f"rs_sma75_{b_name}"] = None
            else:
                sma_rs = compute_rs_from_merged(
                    sma_prep["merged"],
                    [31],
                    day,
                    anchor_ctx=sma_prep["ctx"],
                    stock_asof=sma_prep["stock_asof"],
                    bench_asof=sma_prep["bench_asof"],
                )
                row[f"rs_sma75_{b_name}"] = None if sma_rs.empty else _f(sma_rs.iloc[0].get("rs31"))
        out.append(row)
    return out


def reconcile_last_bar(
    computed: float | None,
    csv_value: float | None,
    *,
    label: str,
    tol: float = ABS_TOL,
) -> None:
    if computed is None and csv_value is None:
        return
    if computed is None or csv_value is None:
        raise ValueError(f"reconcile {label}: computed={computed!r} csv={csv_value!r}")
    if abs(float(computed) - float(csv_value)) > tol:
        raise ValueError(
            f"reconcile {label}: computed={computed} csv={csv_value} "
            f"diff={abs(float(computed) - float(csv_value))} tol={tol}"
        )


def freeze_asof(
    paths: FreezePaths,
    *,
    as_of: date,
    codes: list[str] | None = None,
    exclude_stale_symbols: bool = True,
    reconcile_code: str | None = None,
    overwrite_metrics_from_cache: bool = True,
) -> dict[str, Any]:
    """Build SQLite snapshot. Inputs are read-only. Fail closed on index as-of miss."""
    csv_df = pd.read_csv(paths.csv_path)
    if "code" not in csv_df.columns:
        raise ValueError("CSV missing code column")
    csv_df["code"] = csv_df["code"].astype(str).str.zfill(4)

    topix = load_index_close(paths.index_cache_dir / "topix.csv")
    nikkei = load_index_close(paths.index_cache_dir / "nikkei.csv")
    require_index_asof_bar(index_session_dates(topix), as_of, label="topix")
    require_index_asof_bar(index_session_dates(nikkei), as_of, label="nikkei")

    axis = xtks_axis_dates(as_of, n=AXIS_LEN)
    axis_iso = [d.isoformat() for d in axis]
    benches = {"topix": topix, "nikkei": nikkei}

    if codes is None:
        codes = sorted(csv_df["code"].unique().tolist())

    rows_out: list[dict[str, Any]] = []
    series_out: list[tuple[str, str]] = []
    n_excluded = 0
    reconcile_target = reconcile_code

    for i, code in enumerate(codes):
        if i and i % 50 == 0:
            print(
                f"freeze progress {i}/{len(codes)} kept={len(rows_out)} excluded={n_excluded}",
                flush=True,
            )
        cache_path = paths.daily_cache_dir / f"{code}.csv"
        csv_rows = csv_df[csv_df["code"] == code]
        if csv_rows.empty:
            n_excluded += 1
            continue
        csv_row = csv_rows.iloc[0].to_dict()
        if not cache_path.is_file():
            if exclude_stale_symbols:
                n_excluded += 1
                continue
            raise ValueError(f"missing stock cache for {code}")
        try:
            stock_df = load_stock_ohlc(cache_path)
        except Exception:
            if exclude_stale_symbols:
                n_excluded += 1
                continue
            raise
        stock_dates = {ts.date() for ts in stock_df.index}
        if as_of not in stock_dates:
            if exclude_stale_symbols:
                n_excluded += 1
                continue
            raise ValueError(f"stock {code} missing as-of {as_of}")

        metrics_by_day = _metrics_for_symbol(stock_df, benches, axis)
        metric_keys = sorted(metrics_by_day[0].keys())
        metrics_json_obj = {
            "dates_ref": "meta.axis_dates_json",
            "values": {k: [m.get(k) for m in metrics_by_day] for k in metric_keys},
        }
        last = metrics_by_day[-1]

        if reconcile_target and code == reconcile_target:
            csv_z = csv_row.get("z_turnover_60")
            csv_z_f = None if csv_z is None or pd.isna(csv_z) else float(csv_z)
            reconcile_last_bar(last.get("z_turnover_60"), csv_z_f, label=f"{code}.z_turnover_60")
            if "rs31_topix" in csv_row and not pd.isna(csv_row.get("rs31_topix")):
                reconcile_last_bar(
                    last.get("rs31_topix"),
                    float(csv_row["rs31_topix"]),
                    label=f"{code}.rs31_topix",
                )

        row = dict(csv_row)
        row["date"] = as_of.isoformat()
        if overwrite_metrics_from_cache:
            for k in COMPUTED_ROW_KEYS:
                row[k] = last.get(k)
        else:
            row["rs_sma75_topix"] = last.get("rs_sma75_topix")
            row["rs_sma75_nikkei"] = last.get("rs_sma75_nikkei")
        # price_text is OHLC-derived for the freeze as-of (XLSX parity), not CSV date.
        try:
            mask = [ts.date() <= as_of for ts in stock_df.index]
            stock_upto = stock_df.loc[mask]
            _labels, price_text = compute_candle_descriptors(stock_upto)
            row["candle_labels"] = _labels or None
            row["price_text"] = price_text or None
        except Exception:
            row["candle_labels"] = None
            # keep CSV price_text only as last resort; it may be a different as-of
            row.setdefault("price_text", None)

        rows_out.append(row)
        series_out.append(
            (code, json.dumps(metrics_json_obj, ensure_ascii=False, separators=(",", ":")))
        )

    paths.out_sqlite.parent.mkdir(parents=True, exist_ok=True)
    if paths.out_sqlite.exists():
        paths.out_sqlite.unlink()
    conn = sqlite3.connect(paths.out_sqlite)
    try:
        conn.execute(
            """
            CREATE TABLE meta (
              as_of TEXT NOT NULL,
              source_csv_sha256 TEXT NOT NULL,
              freeze_utc TEXT NOT NULL,
              n_rows INTEGER NOT NULL,
              n_excluded INTEGER NOT NULL,
              axis_dates_json TEXT NOT NULL,
              note TEXT
            )
            """
        )
        conn.execute("CREATE TABLE rows (code TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE series (code TEXT PRIMARY KEY, metrics_json TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO meta VALUES (?,?,?,?,?,?,?)",
            (
                as_of.isoformat(),
                _sha256_file(paths.csv_path),
                datetime.now(timezone.utc).isoformat(),
                len(rows_out),
                n_excluded,
                json.dumps(axis_iso, separators=(",", ":")),
                "prototype freeze; metrics+price_text from cache as-of; "
                "CSV identity/links/news may be from a different CSV date; not Track D",
            ),
        )
        conn.executemany(
            "INSERT INTO rows(code, payload_json) VALUES (?,?)",
            [
                (
                    str(r["code"]).zfill(4),
                    json.dumps(_json_sanitize(r), ensure_ascii=False, separators=(",", ":")),
                )
                for r in rows_out
            ],
        )
        conn.executemany("INSERT INTO series(code, metrics_json) VALUES (?,?)", series_out)
        conn.commit()
    finally:
        conn.close()

    return {
        "as_of": as_of.isoformat(),
        "n_rows": len(rows_out),
        "n_excluded": n_excluded,
        "axis_len": len(axis),
        "sqlite": str(paths.out_sqlite),
    }
