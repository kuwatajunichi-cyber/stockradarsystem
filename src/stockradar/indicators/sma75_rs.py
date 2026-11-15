"""SMA75 series + B-method RS (window 31). Not close RS75."""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockradar.indicators.date_anchor import merged_close
from stockradar.indicators.rs import compute_rs_from_merged


def sma_series(close: pd.Series, window: int = 75) -> pd.Series:
    s = close.astype(float)
    return s.rolling(window=window, min_periods=window).mean()


def compute_rs_sma75_from_closes(
    stock_close: pd.Series,
    bench_close: pd.Series,
    run_date: date,
    *,
    sma_window: int = 75,
    rs_window: int = 31,
) -> float | None:
    stock_sma = sma_series(stock_close, sma_window).dropna()
    bench_sma = sma_series(bench_close, sma_window).dropna()
    if stock_sma.empty or bench_sma.empty:
        return None
    stock_df = pd.DataFrame({"Close": stock_sma})
    bench_df = pd.DataFrame({"Close": bench_sma})
    merged = merged_close(stock_df, bench_df)
    out = compute_rs_from_merged(merged, [rs_window], run_date)
    if out.empty:
        return None
    val = out.iloc[0].get(f"rs{rs_window}")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return float(val)


def compute_close_rs75_from_closes(
    stock_close: pd.Series,
    bench_close: pd.Series,
    run_date: date,
) -> float | None:
    """Close-price RS75 for contrast tests (must differ from SMA75 RS31)."""
    stock_df = pd.DataFrame({"Close": stock_close.astype(float)})
    bench_df = pd.DataFrame({"Close": bench_close.astype(float)})
    merged = merged_close(stock_df, bench_df)
    out = compute_rs_from_merged(merged, [75], run_date)
    if out.empty:
        return None
    val = out.iloc[0].get("rs75")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return float(val)
