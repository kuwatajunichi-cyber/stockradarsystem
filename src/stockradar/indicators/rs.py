"""
RS（B方式：期間リターン差）と短期RS加速の計算。
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockradar.indicators.date_anchor import (
    AsofSeries,
    AnchorContext,
    anchored_return,
    build_anchor_context,
    merged_close,
    nth_business_anchor,
    prepare_asof_series,
    resolve_run_anchor_date,
)


def compute_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    windows: list[int],
    run_date: date,
) -> pd.DataFrame:
    merged = merged_close(stock_df, bench_df)
    return compute_rs_from_merged(merged, windows, run_date)


def compute_rs_from_merged(
    merged: pd.DataFrame,
    windows: list[int],
    run_date: date,
    *,
    anchor_ctx: AnchorContext | None = None,
    stock_asof: AsofSeries | None = None,
    bench_asof: AsofSeries | None = None,
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
    ctx = anchor_ctx or build_anchor_context(merged.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    cols = [f"rs{T}" for T in windows]
    if run_anchor is None:
        return pd.DataFrame([{c: None for c in cols}], index=[pd.Timestamp(run_date)])
    stock_ready = stock_asof or prepare_asof_series(merged["stock_close"])
    bench_ready = bench_asof or prepare_asof_series(merged["bench_close"])

    row: dict[str, float | None] = {}
    for T in windows:
        start_anchor = nth_business_anchor(ctx, run_anchor, T)
        if start_anchor is None:
            row[f"rs{T}"] = None
            continue
        stock_ret = anchored_return(stock_ready, run_anchor, start_anchor)
        bench_ret = anchored_return(bench_ready, run_anchor, start_anchor)
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
    merged = merged_close(stock_df, bench_df)
    return compute_rs_acceleration_from_merged(
        merged,
        run_date,
        short_window=short_window,
        long_window=long_window,
    )


def compute_rs_acceleration_from_merged(
    merged: pd.DataFrame,
    run_date: date,
    *,
    short_window: int = 31,
    long_window: int = 252,
    anchor_ctx: AnchorContext | None = None,
    stock_asof: AsofSeries | None = None,
    bench_asof: AsofSeries | None = None,
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
    ctx = anchor_ctx or build_anchor_context(merged.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    stock_ready = stock_asof or prepare_asof_series(merged["stock_close"])
    bench_ready = bench_asof or prepare_asof_series(merged["bench_close"])

    short_anchor = nth_business_anchor(ctx, run_anchor, short_window)
    long_anchor = nth_business_anchor(ctx, run_anchor, long_window)
    if short_anchor is None or long_anchor is None:
        return pd.Series([None], index=[run_anchor])

    stock_ret_short = anchored_return(stock_ready, run_anchor, short_anchor)
    bench_ret_short = anchored_return(bench_ready, run_anchor, short_anchor)
    stock_ret_long = anchored_return(stock_ready, run_anchor, long_anchor)
    bench_ret_long = anchored_return(bench_ready, run_anchor, long_anchor)
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
    merged = merged_close(stock_df, bench_df)
    return compute_rs_acceleration_zscore_from_merged(
        merged,
        run_date,
        lookback_days=lookback_days,
        short_window=short_window,
        long_window=long_window,
    )


def compute_rs_acceleration_zscore_from_merged(
    merged: pd.DataFrame,
    run_date: date,
    *,
    lookback_days: int,
    short_window: int = 31,
    long_window: int = 252,
    anchor_ctx: AnchorContext | None = None,
    stock_asof: AsofSeries | None = None,
    bench_asof: AsofSeries | None = None,
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
    ctx = anchor_ctx or build_anchor_context(merged.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    stock_ready = stock_asof or prepare_asof_series(merged["stock_close"])
    bench_ready = bench_asof or prepare_asof_series(merged["bench_close"])

    eligible = ctx.index[ctx.index <= run_anchor]
    sample = eligible[-lookback_days:]
    values: list[float] = []
    for dt in sample:
        short_anchor = nth_business_anchor(ctx, dt, short_window)
        long_anchor = nth_business_anchor(ctx, dt, long_window)
        if short_anchor is None or long_anchor is None:
            continue
        stock_ret_short = anchored_return(stock_ready, dt, short_anchor)
        bench_ret_short = anchored_return(bench_ready, dt, short_anchor)
        stock_ret_long = anchored_return(stock_ready, dt, long_anchor)
        bench_ret_long = anchored_return(bench_ready, dt, long_anchor)
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
