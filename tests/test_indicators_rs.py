"""
RS（B方式）と短期RS加速のテスト。
compute_rs, compute_rs_acceleration, compute_rs_acceleration_zscore を検証する。
"""
from __future__ import annotations

import pandas as pd
import pytest

from stockradar.indicators.rs import (
    compute_rs,
    compute_rs_acceleration,
    compute_rs_acceleration_zscore,
)


@pytest.fixture
def stock_df() -> pd.DataFrame:
    """10日分の銘柄 Close（1日目100→2日目102で+2%など）。"""
    dates = pd.DatetimeIndex(
        pd.date_range("2026-01-01", periods=10, freq="B"),
        name="date",
    )
    # 100, 102, 104, 106, 108, 110, 112, 114, 116, 118（日次約+2%）
    close = [100.0, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    return pd.DataFrame({"Close": close}, index=dates)


@pytest.fixture
def bench_df() -> pd.DataFrame:
    """10日分のベンチ Close（1日目100→2日目101で+1%など）。"""
    dates = pd.DatetimeIndex(
        pd.date_range("2026-01-01", periods=10, freq="B"),
        name="date",
    )
    # 100, 101, 102, 103, 104, 105, 106, 107, 108, 109（日次約+1%）
    close = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    return pd.DataFrame({"Close": close}, index=dates)


def test_compute_rs_returns_dataframe_with_rs_columns(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_rs が DataFrame を返し、index が merge と一致し rs1/rs2 列が存在すること。"""
    result = compute_rs(stock_df, bench_df, windows=[1, 2])
    assert isinstance(result, pd.DataFrame)
    assert result.index.equals(stock_df.index)
    assert "rs1" in result.columns
    assert "rs2" in result.columns


def test_compute_rs_one_period_return_difference(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """1期リターン差が期待値と一致すること（銘柄+2%、ベンチ+1% → rs1=0.01）。"""
    result = compute_rs(stock_df, bench_df, windows=[1])
    # 2日目: 銘柄 (102/100 - 1)=0.02, ベンチ (101/100 - 1)=0.01 → rs1 = 0.01
    rs1_day2 = result["rs1"].iloc[1]
    assert rs1_day2 == pytest.approx(0.01, rel=1e-9)


def test_compute_rs_acceleration_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_rs_acceleration が Series を返し長さが入力と整合すること。"""
    result = compute_rs_acceleration(
        stock_df, bench_df, short_window=1, long_window=2
    )
    assert isinstance(result, pd.Series)
    assert len(result) == len(stock_df)
    assert result.index.equals(stock_df.index)


def test_compute_rs_acceleration_zscore_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_rs_acceleration_zscore が Series を返すこと。"""
    # min_periods = max(20, int(lookback_days*0.7)) のため lookback_days >= 21 が必要
    result = compute_rs_acceleration_zscore(
        stock_df, bench_df, lookback_days=21, short_window=1, long_window=2
    )
    assert isinstance(result, pd.Series)
    assert len(result) == len(stock_df)


def test_compute_rs_acceleration_zscore_leading_nan(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """窓不足で先頭が NaN になること。"""
    result = compute_rs_acceleration_zscore(
        stock_df, bench_df, lookback_days=21, short_window=1, long_window=2
    )
    # shift(long_window) と rolling(min_periods) のため先頭は NaN
    assert pd.isna(result.iloc[0])
