from __future__ import annotations

from datetime import date
from typing import NamedTuple

import numpy as np
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


class AnchorContext(NamedTuple):
    index: pd.DatetimeIndex
    index_ns: np.ndarray


class AsofSeries(NamedTuple):
    index_ns: np.ndarray
    values: np.ndarray


def build_anchor_context(index: pd.Index) -> AnchorContext:
    idx = pd.to_datetime(index).sort_values().unique()
    return AnchorContext(index=idx, index_ns=idx.view("i8"))


def resolve_run_anchor_date(index: pd.Index | AnchorContext, run_date: date) -> pd.Timestamp | None:
    if isinstance(index, AnchorContext):
        idx = index.index
    else:
        idx = pd.to_datetime(index)
    candidates = idx[idx.date <= run_date]
    if len(candidates) == 0:
        return None
    return pd.Timestamp(candidates.max())


def nth_business_anchor(index: pd.Index | AnchorContext, run_anchor: pd.Timestamp, days_back: int) -> pd.Timestamp | None:
    if isinstance(index, AnchorContext):
        ctx = index
    else:
        ctx = build_anchor_context(index)
    pos = int(np.searchsorted(ctx.index_ns, run_anchor.value, side="right") - 1)
    target = pos - days_back
    if target < 0:
        return None
    return pd.Timestamp(ctx.index[target])


def prepare_asof_series(series: pd.Series) -> AsofSeries:
    s = series.dropna().sort_index()
    if s.empty:
        return AsofSeries(index_ns=np.array([], dtype=np.int64), values=np.array([], dtype=float))
    return AsofSeries(index_ns=s.index.view("i8"), values=s.to_numpy(dtype=float, copy=False))


def asof_value(series: pd.Series | AsofSeries, anchor: pd.Timestamp) -> float | None:
    if isinstance(series, AsofSeries):
        idx_ns = series.index_ns
        vals = series.values
    else:
        prepared = prepare_asof_series(series)
        idx_ns = prepared.index_ns
        vals = prepared.values
    if len(idx_ns) == 0:
        return None
    pos = int(np.searchsorted(idx_ns, anchor.value, side="right") - 1)
    if pos < 0:
        return None
    return float(vals[pos])


def anchored_return(series: pd.Series | AsofSeries, end_anchor: pd.Timestamp, start_anchor: pd.Timestamp) -> float | None:
    end_v = asof_value(series, end_anchor)
    start_v = asof_value(series, start_anchor)
    if end_v is None or start_v is None or start_v == 0:
        return None
    return end_v / start_v - 1.0

