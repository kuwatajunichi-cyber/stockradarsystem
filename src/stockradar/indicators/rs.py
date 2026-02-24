"""
RS（B方式：期間リターン差）と短期RS加速の計算。
"""
from __future__ import annotations

import pandas as pd


def compute_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    windows: list[int],
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
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    result = pd.DataFrame(index=merged.index)
    for T in windows:
        stock_ret = merged["stock_close"] / merged["stock_close"].shift(T) - 1
        bench_ret = merged["bench_close"] / merged["bench_close"].shift(T) - 1
        rs_T = stock_ret - bench_ret
        result[f"rs{T}"] = rs_T

    return result


def compute_rs_acceleration(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
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
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    stock_ret_short = merged["stock_close"] / merged["stock_close"].shift(short_window) - 1
    bench_ret_short = merged["bench_close"] / merged["bench_close"].shift(short_window) - 1
    rs_short = stock_ret_short - bench_ret_short

    stock_ret_long = merged["stock_close"] / merged["stock_close"].shift(long_window) - 1
    bench_ret_long = merged["bench_close"] / merged["bench_close"].shift(long_window) - 1
    rs_long = stock_ret_long - bench_ret_long

    rs_acceleration = rs_short - rs_long
    return rs_acceleration


def compute_rs_acceleration_zscore(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
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
    rs_acceleration = compute_rs_acceleration(
        stock_df, bench_df, short_window, long_window
    )

    min_periods = max(20, int(lookback_days * 0.7))
    rs_accel_mean = rs_acceleration.rolling(
        window=lookback_days, min_periods=min_periods
    ).mean()
    rs_accel_std = rs_acceleration.rolling(
        window=lookback_days, min_periods=min_periods
    ).std()
    rs_acceleration_zscore = (rs_acceleration - rs_accel_mean) / rs_accel_std

    return rs_acceleration_zscore
