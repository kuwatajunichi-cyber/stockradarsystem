"""
出来高zscore（売買代金近似ベース）の計算。
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from stockradar.indicators.date_anchor import (
    AnchorContext,
    build_anchor_context,
    normalize_utc_naive_index,
    nth_business_anchor,
    resolve_run_anchor_date,
)


def compute_zscore_turnover(
    df: pd.DataFrame,
    lookback_days: int,
    run_date: date,
) -> pd.Series:
    out = df.copy()
    out.index = normalize_utc_naive_index(out.index)
    out = out.sort_index()
    ctx = build_anchor_context(out.index)
    return compute_zscore_turnover_from_prepared(
        out,
        lookback_days,
        run_date,
        anchor_ctx=ctx,
    )


def compute_zscore_turnover_from_prepared(
    out: pd.DataFrame,
    lookback_days: int,
    run_date: date,
    *,
    anchor_ctx: AnchorContext | None = None,
) -> pd.Series:
    """
    出来高zscore（売買代金近似ベース）を計算。

    Args:
        df: DataFrame（Close, Volume列、date index）
        lookback_days: 窓サイズ（営業日数）

    Returns:
        Series（z_turnover）
    """
    out_local = out.copy()
    out_local.index = normalize_utc_naive_index(out_local.index)

    ctx = anchor_ctx or build_anchor_context(out_local.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    start_anchor = nth_business_anchor(ctx, run_anchor, lookback_days)
    if start_anchor is None:
        return pd.Series([None], index=[run_anchor])

    window_df = out_local[(out_local.index > start_anchor) & (out_local.index <= run_anchor)]
    turnover_yen = window_df["Close"] * window_df["Volume"]
    log_turnover = np.log1p(turnover_yen)
    min_periods = max(20, int(lookback_days * 0.7))
    valid_n = int(turnover_yen.dropna().shape[0])
    if valid_n < min_periods:
        return pd.Series([None], index=[run_anchor])
    if pd.isna(log_turnover.iloc[-1]):
        return pd.Series([None], index=[run_anchor])
    std = float(log_turnover.std())
    if std == 0 or np.isnan(std):
        return pd.Series([None], index=[run_anchor])
    z_val = float((log_turnover.iloc[-1] - log_turnover.mean()) / std)
    return pd.Series([z_val], index=[run_anchor])


def compute_turnover_ma_ratio_from_prepared(
    out: pd.DataFrame,
    lookback_days: int,
    run_date: date,
    *,
    anchor_ctx: AnchorContext | None = None,
) -> pd.Series:
    """
    売買代金（Close*Volume）の、直近 lookback_days 営業日（アンカー当日を含む窓）の単純平均に対する倍率。

    窓の切り方・最小本数判定は compute_zscore_turnover_from_prepared と同一。
    """
    out_local = out.copy()
    out_local.index = normalize_utc_naive_index(out_local.index)

    ctx = anchor_ctx or build_anchor_context(out_local.index)
    run_anchor = resolve_run_anchor_date(ctx, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    start_anchor = nth_business_anchor(ctx, run_anchor, lookback_days)
    if start_anchor is None:
        return pd.Series([None], index=[run_anchor])

    window_df = out_local[(out_local.index > start_anchor) & (out_local.index <= run_anchor)]
    turnover_yen = window_df["Close"] * window_df["Volume"]
    min_periods = max(20, int(lookback_days * 0.7))
    valid_n = int(turnover_yen.dropna().shape[0])
    if valid_n < min_periods:
        return pd.Series([None], index=[run_anchor])

    mean_v = float(turnover_yen.mean())
    curr_v = float(turnover_yen.iloc[-1])
    if mean_v <= 0 or np.isnan(mean_v) or np.isnan(curr_v):
        return pd.Series([None], index=[run_anchor])
    ratio = curr_v / mean_v
    return pd.Series([ratio], index=[run_anchor])
