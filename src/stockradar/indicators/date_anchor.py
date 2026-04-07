from __future__ import annotations

from datetime import date

import pandas as pd


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def merged_close(stock_df: pd.DataFrame, bench_df: pd.DataFrame) -> pd.DataFrame:
    stock = _normalize_index(stock_df)[["Close"]].rename(columns={"Close": "stock_close"})
    bench = _normalize_index(bench_df)[["Close"]].rename(columns={"Close": "bench_close"})
    merged = pd.merge(stock, bench, left_index=True, right_index=True, how="outer")
    return merged.sort_index()


def resolve_run_anchor_date(index: pd.Index, run_date: date) -> pd.Timestamp | None:
    idx = pd.to_datetime(index)
    candidates = idx[idx.date <= run_date]
    if len(candidates) == 0:
        return None
    return pd.Timestamp(candidates.max())


def nth_business_anchor(index: pd.Index, run_anchor: pd.Timestamp, days_back: int) -> pd.Timestamp | None:
    idx = pd.to_datetime(index).sort_values().unique()
    eligible = idx[idx <= run_anchor]
    if len(eligible) <= days_back:
        return None
    return pd.Timestamp(eligible[-(days_back + 1)])


def asof_value(series: pd.Series, anchor: pd.Timestamp) -> float | None:
    s = series.dropna().sort_index()
    s = s[s.index <= anchor]
    if s.empty:
        return None
    return float(s.iloc[-1])


def anchored_return(series: pd.Series, end_anchor: pd.Timestamp, start_anchor: pd.Timestamp) -> float | None:
    end_v = asof_value(series, end_anchor)
    start_v = asof_value(series, start_anchor)
    if end_v is None or start_v is None or start_v == 0:
        return None
    return end_v / start_v - 1.0

