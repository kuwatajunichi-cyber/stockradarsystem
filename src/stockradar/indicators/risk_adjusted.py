"""
β調整RS、情報比率などリスク調整済み指標の計算。
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from stockradar.indicators.date_anchor import (
    AsofSeries,
    AnchorContext,
    anchored_return,
    build_anchor_context,
    merged_close,
    nth_business_anchor,
    prepare_asof_series,
    normalize_utc_naive_index,
    resolve_run_anchor_date,
)


def compute_beta_adjusted_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    run_date: date,
    beta_window: int = 126,
    return_window: int = 252,
) -> pd.Series:
    merged = merged_close(stock_df, bench_df)
    return compute_beta_adjusted_rs_from_merged(
        merged,
        run_date,
        beta_window=beta_window,
        return_window=return_window,
    )


def compute_beta_adjusted_rs_from_merged(
    merged: pd.DataFrame,
    run_date: date,
    *,
    beta_window: int = 126,
    return_window: int = 252,
    anchor_ctx: AnchorContext | None = None,
    stock_asof: AsofSeries | None = None,
    bench_asof: AsofSeries | None = None,
) -> pd.Series:
    """
    β調整RS（Market-adjusted Excess Return）を計算。
    βを推定し、市場寄与分を差し引いた純粋な銘柄固有要因の強さを測定。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        beta_window: β推定窓（営業日数、default=126）
        return_window: 累積リターン計算窓（営業日数、default=252）

    Returns:
        Series（beta_adjusted_rs）
    """
    merged_local = merged.copy()
    merged_local.index = normalize_utc_naive_index(merged_local.index)
    ctx = anchor_ctx or build_anchor_context(merged_local.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    start_anchor = nth_business_anchor(ctx, run_anchor, return_window)
    if start_anchor is None:
        return pd.Series([None], index=[run_anchor])

    beta_end = start_anchor
    beta_start = nth_business_anchor(ctx, beta_end, beta_window)
    if beta_start is None:
        return pd.Series([None], index=[run_anchor])

    beta_slice = merged_local[
        (merged_local.index > beta_start) & (merged_local.index <= beta_end)
    ]
    stock_ret = beta_slice["stock_close"].ffill().pct_change().dropna()
    bench_ret = beta_slice["bench_close"].ffill().pct_change().dropna()
    rets = pd.concat([stock_ret, bench_ret], axis=1, join="inner").dropna()
    min_periods = max(20, int(beta_window * 0.7))
    if len(rets) < min_periods:
        return pd.Series([None], index=[run_anchor])
    bench_var = float(np.var(rets.iloc[:, 1].to_numpy()))
    if bench_var == 0:
        return pd.Series([None], index=[run_anchor])
    cov = float(np.cov(rets.iloc[:, 0].to_numpy(), rets.iloc[:, 1].to_numpy(), ddof=0)[0, 1])
    beta = cov / bench_var

    stock_ready = stock_asof or prepare_asof_series(merged_local["stock_close"])
    bench_ready = bench_asof or prepare_asof_series(merged_local["bench_close"])
    stock_cumret = anchored_return(stock_ready, run_anchor, start_anchor)
    bench_cumret = anchored_return(bench_ready, run_anchor, start_anchor)
    if stock_cumret is None or bench_cumret is None:
        return pd.Series([None], index=[run_anchor])
    beta_adjusted_rs = stock_cumret - (beta * bench_cumret)
    return pd.Series([beta_adjusted_rs], index=[run_anchor])


def compute_information_ratio(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    run_date: date,
    window: int = 63,
) -> pd.Series:
    merged = merged_close(stock_df, bench_df)
    return compute_information_ratio_from_merged(
        merged,
        run_date,
        window=window,
    )


def compute_information_ratio_from_merged(
    merged: pd.DataFrame,
    run_date: date,
    *,
    window: int = 63,
    anchor_ctx: AnchorContext | None = None,
) -> pd.Series:
    """
    情報比率（Information Ratio）を計算。
    日次超過リターンの平均を標準偏差で割った値。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        window: 情報比率窓（営業日数、default=63）

    Returns:
        Series（information_ratio）
    """
    merged_local = merged.copy()
    merged_local.index = normalize_utc_naive_index(merged_local.index)
    ctx = anchor_ctx or build_anchor_context(merged_local.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    start_anchor = nth_business_anchor(ctx, run_anchor, window)
    if start_anchor is None:
        return pd.Series([None], index=[run_anchor])

    window_slice = merged_local[
        (merged_local.index > start_anchor) & (merged_local.index <= run_anchor)
    ]
    stock_ret = window_slice["stock_close"].ffill().pct_change().dropna()
    bench_ret = window_slice["bench_close"].ffill().pct_change().dropna()
    excess = pd.concat([stock_ret, bench_ret], axis=1, join="inner").dropna()
    min_periods = max(20, int(window * 0.7))
    if len(excess) < min_periods:
        return pd.Series([None], index=[run_anchor])
    excess_ret = excess.iloc[:, 0] - excess.iloc[:, 1]
    std = float(excess_ret.std())
    if std == 0 or pd.isna(std):
        return pd.Series([None], index=[run_anchor])
    info_ratio = float(excess_ret.mean() / std)
    return pd.Series([info_ratio], index=[run_anchor])
