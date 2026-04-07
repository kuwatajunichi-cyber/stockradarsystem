"""
RS（B方式）と短期RS加速のテスト。
compute_rs, compute_rs_acceleration, compute_rs_acceleration_zscore を検証する。
"""
from __future__ import annotations

from datetime import date

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
    """compute_rs が run_date アンカー1行の DataFrame を返し rs列が存在すること。"""
    result = compute_rs(stock_df, bench_df, windows=[1, 2], run_date=date(2026, 1, 14))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 1
    assert "rs1" in result.columns
    assert "rs2" in result.columns


def test_compute_rs_one_period_return_difference(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """1期リターン差が期待値と一致すること（銘柄+2%、ベンチ+1% → rs1=0.01）。"""
    result = compute_rs(stock_df, bench_df, windows=[1], run_date=date(2026, 1, 14))
    rs1 = result["rs1"].iloc[0]
    assert rs1 == pytest.approx(118 / 116 - 109 / 108, rel=1e-9)


def test_compute_rs_acceleration_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_rs_acceleration が run_date アンカー1点の Series を返すこと。"""
    result = compute_rs_acceleration(
        stock_df, bench_df, date(2026, 1, 14), short_window=1, long_window=2
    )
    assert isinstance(result, pd.Series)
    assert len(result) == 1


def test_compute_rs_acceleration_zscore_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_rs_acceleration_zscore が Series を返すこと。"""
    # データが短いため min_periods を満たせず None になるが、返り型は維持
    result = compute_rs_acceleration_zscore(
        stock_df, bench_df, date(2026, 1, 14), lookback_days=21, short_window=1, long_window=2
    )
    assert isinstance(result, pd.Series)
    assert len(result) == 1


def test_compute_rs_acceleration_zscore_leading_nan(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """窓不足時はアンカー値が NaN/None になること。"""
    result = compute_rs_acceleration_zscore(
        stock_df, bench_df, date(2026, 1, 14), lookback_days=21, short_window=1, long_window=2
    )
    assert pd.isna(result.iloc[0])
