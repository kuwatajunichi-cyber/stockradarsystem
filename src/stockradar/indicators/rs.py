"""
RS（B方式：期間リターン差）と短期RS加速の計算。
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockradar.indicators.date_anchor import (
    anchored_return,
    merged_close,
    nth_business_anchor,
    resolve_run_anchor_date,
)


def compute_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    windows: list[int],
    run_date: date,
) -> pd.DataFrame:
    """
    RS（B方式：期間リターン差）を計算。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        windows: 期間リスト（営業日数）

    Returns:
        DataFrame（rs_T列）
    """
    merged = merged_close(stock_df, bench_df)
    run_anchor = resolve_run_anchor_date(merged.index, run_date)
    cols = [f"rs{T}" for T in windows]
    if run_anchor is None:
        return pd.DataFrame([{c: None for c in cols}], index=[pd.Timestamp(run_date)])

    row: dict[str, float | None] = {}
    for T in windows:
        start_anchor = nth_business_anchor(merged.index, run_anchor, T)
        if start_anchor is None:
            row[f"rs{T}"] = None
            continue
        stock_ret = anchored_return(merged["stock_close"], run_anchor, start_anchor)
        bench_ret = anchored_return(merged["bench_close"], run_anchor, start_anchor)
        if stock_ret is None or bench_ret is None:
            row[f"rs{T}"] = None
        else:
            row[f"rs{T}"] = stock_ret - bench_ret

    return pd.DataFrame([row], index=[run_anchor])


def compute_rs_acceleration(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    run_date: date,
    short_window: int = 31,
    long_window: int = 252,
) -> pd.Series:
    """
    短期RS加速（Short-term RS Acceleration）を計算。
    短期RSと長期RSの差を算出。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        short_window: 短期窓（営業日数、default=31）
        long_window: 長期窓（営業日数、default=252）

    Returns:
        Series（rs_acceleration）
    """
    merged = merged_close(stock_df, bench_df)
    run_anchor = resolve_run_anchor_date(merged.index, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])

    short_anchor = nth_business_anchor(merged.index, run_anchor, short_window)
    long_anchor = nth_business_anchor(merged.index, run_anchor, long_window)
    if short_anchor is None or long_anchor is None:
        return pd.Series([None], index=[run_anchor])

    stock_ret_short = anchored_return(merged["stock_close"], run_anchor, short_anchor)
    bench_ret_short = anchored_return(merged["bench_close"], run_anchor, short_anchor)
    stock_ret_long = anchored_return(merged["stock_close"], run_anchor, long_anchor)
    bench_ret_long = anchored_return(merged["bench_close"], run_anchor, long_anchor)
    if (
        stock_ret_short is None
        or bench_ret_short is None
        or stock_ret_long is None
        or bench_ret_long is None
    ):
        return pd.Series([None], index=[run_anchor])

    rs_short = stock_ret_short - bench_ret_short
    rs_long = stock_ret_long - bench_ret_long
    return pd.Series([rs_short - rs_long], index=[run_anchor])


def compute_rs_acceleration_zscore(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    run_date: date,
    lookback_days: int,
    short_window: int = 31,
    long_window: int = 252,
) -> pd.Series:
    """
    短期RS加速のzscoreを計算。
    短期RS加速を標準化窓で標準化した値。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        lookback_days: 標準化窓（営業日数、売買代金zscoreと同じ）
        short_window: 短期窓（営業日数、default=31）
        long_window: 長期窓（営業日数、default=252）

    Returns:
        Series（rs_acceleration_zscore）
    """
    merged = merged_close(stock_df, bench_df)
    run_anchor = resolve_run_anchor_date(merged.index, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])

    all_idx = pd.to_datetime(merged.index).sort_values().unique()
    eligible = all_idx[all_idx <= run_anchor]
    sample = eligible[-lookback_days:]
    values: list[float] = []
    for dt in sample:
        short_anchor = nth_business_anchor(all_idx, dt, short_window)
        long_anchor = nth_business_anchor(all_idx, dt, long_window)
        if short_anchor is None or long_anchor is None:
            continue
        stock_ret_short = anchored_return(merged["stock_close"], dt, short_anchor)
        bench_ret_short = anchored_return(merged["bench_close"], dt, short_anchor)
        stock_ret_long = anchored_return(merged["stock_close"], dt, long_anchor)
        bench_ret_long = anchored_return(merged["bench_close"], dt, long_anchor)
        if (
            stock_ret_short is None
            or bench_ret_short is None
            or stock_ret_long is None
            or bench_ret_long is None
        ):
            continue
        values.append((stock_ret_short - bench_ret_short) - (stock_ret_long - bench_ret_long))

    min_periods = max(20, int(lookback_days * 0.7))
    if len(values) < min_periods:
        return pd.Series([None], index=[run_anchor])
    s = pd.Series(values)
    std = s.std()
    if std == 0 or pd.isna(std):
        return pd.Series([None], index=[run_anchor])
    z = (s.iloc[-1] - s.mean()) / std
    return pd.Series([z], index=[run_anchor])
