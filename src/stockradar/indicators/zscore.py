"""
出来高zscore（売買代金近似ベース）の計算。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_zscore_turnover(df: pd.DataFrame, lookback_days: int) -> pd.Series:
    """
    出来高zscore（売買代金近似ベース）を計算。

    Args:
        df: DataFrame（Close, Volume列、date index）
        lookback_days: 窓サイズ（営業日数）

    Returns:
        Series（z_turnover）
    """
    turnover_yen = df["Close"] * df["Volume"]
    log_turnover = np.log1p(turnover_yen)
    min_periods = max(20, int(lookback_days * 0.7))
    z_turnover = (log_turnover - log_turnover.rolling(window=lookback_days, min_periods=min_periods).mean()) / log_turnover.rolling(window=lookback_days, min_periods=min_periods).std()
    return z_turnover
