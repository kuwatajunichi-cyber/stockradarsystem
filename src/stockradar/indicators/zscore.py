"""
出来高zscore（売買代金近似ベース）の計算。
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from stockradar.indicators.date_anchor import (
    nth_business_anchor,
    resolve_run_anchor_date,
)


def compute_zscore_turnover(
    df: pd.DataFrame,
    lookback_days: int,
    run_date: date,
) -> pd.Series:
    """
    出来高zscore（売買代金近似ベース）を計算。

    Args:
        df: DataFrame（Close, Volume列、date index）
        lookback_days: 窓サイズ（営業日数）

    Returns:
        Series（z_turnover）
    """
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    run_anchor = resolve_run_anchor_date(out.index, run_date)
    if run_anchor is None:
        return pd.Series([None], index=[pd.Timestamp(run_date)])
    start_anchor = nth_business_anchor(out.index, run_anchor, lookback_days)
    if start_anchor is None:
        return pd.Series([None], index=[run_anchor])

    window_df = out[(out.index > start_anchor) & (out.index <= run_anchor)]
    turnover_yen = window_df["Close"] * window_df["Volume"]
    log_turnover = np.log1p(turnover_yen)
    min_periods = max(20, int(lookback_days * 0.7))
    if len(log_turnover) < min_periods:
        return pd.Series([None], index=[run_anchor])
    std = float(log_turnover.std())
    if std == 0 or np.isnan(std):
        return pd.Series([None], index=[run_anchor])
    z_val = float((log_turnover.iloc[-1] - log_turnover.mean()) / std)
    return pd.Series([z_val], index=[run_anchor])
