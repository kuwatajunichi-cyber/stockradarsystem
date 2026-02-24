"""
β調整RS、情報比率などリスク調整済み指標の計算。
"""
from __future__ import annotations

import pandas as pd


def compute_beta_adjusted_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    beta_window: int = 126,
    return_window: int = 252,
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
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    stock_ret = merged["stock_close"].pct_change()
    bench_ret = merged["bench_close"].pct_change()

    min_periods = max(20, int(beta_window * 0.7))
    stock_mean = stock_ret.rolling(
        window=beta_window, min_periods=min_periods
    ).mean()
    bench_mean = bench_ret.rolling(
        window=beta_window, min_periods=min_periods
    ).mean()
    cov = (
        (stock_ret - stock_mean) * (bench_ret - bench_mean)
    ).rolling(window=beta_window, min_periods=min_periods).mean()
    bench_var = bench_ret.rolling(
        window=beta_window, min_periods=min_periods
    ).var()
    beta = cov / bench_var

    stock_cumret = (
        merged["stock_close"] / merged["stock_close"].shift(return_window) - 1
    )
    bench_cumret = (
        merged["bench_close"] / merged["bench_close"].shift(return_window) - 1
    )

    beta_at_start = beta.shift(return_window)
    market_contribution = beta_at_start * bench_cumret
    beta_adjusted_rs = stock_cumret - market_contribution

    return beta_adjusted_rs


def compute_information_ratio(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    window: int = 63,
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
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    stock_ret = merged["stock_close"].pct_change()
    bench_ret = merged["bench_close"].pct_change()
    excess_ret = stock_ret - bench_ret

    min_periods = max(20, int(window * 0.7))
    mean_excess = excess_ret.rolling(
        window=window, min_periods=min_periods
    ).mean()
    std_excess = excess_ret.rolling(
        window=window, min_periods=min_periods
    ).std()
    information_ratio = mean_excess / std_excess

    return information_ratio
