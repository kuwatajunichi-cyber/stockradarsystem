"""
β調整RS・情報比率のテスト。
compute_beta_adjusted_rs, compute_information_ratio を検証する。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stockradar.indicators.risk_adjusted import (
    compute_beta_adjusted_rs,
    compute_information_ratio,
)


@pytest.fixture
def stock_df() -> pd.DataFrame:
    """短い日付 index と Close 列の銘柄 DataFrame。"""
    dates = pd.DatetimeIndex(
        pd.date_range("2026-01-01", periods=25, freq="B"),
        name="date",
    )
    # 日次約+1%
    close = [100.0 * (1.01**i) for i in range(25)]
    return pd.DataFrame({"Close": close}, index=dates)


@pytest.fixture
def bench_df() -> pd.DataFrame:
    """短い日付 index と Close 列のベンチ DataFrame。"""
    dates = pd.DatetimeIndex(
        pd.date_range("2026-01-01", periods=25, freq="B"),
        name="date",
    )
    # 日次約+0.5%（銘柄より低い）
    close = [100.0 * (1.005**i) for i in range(25)]
    return pd.DataFrame({"Close": close}, index=dates)


def test_compute_beta_adjusted_rs_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_beta_adjusted_rs が run_date アンカー1点の Series を返すこと。"""
    # min_periods = max(20, int(beta_window*0.7)) のため beta_window >= 21 が必要
    result = compute_beta_adjusted_rs(
        stock_df, bench_df, date(2026, 2, 4), beta_window=21, return_window=21
    )
    assert isinstance(result, pd.Series)
    assert len(result) == 1


def test_compute_information_ratio_returns_series(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """compute_information_ratio が Series を返すこと。"""
    result = compute_information_ratio(stock_df, bench_df, date(2026, 2, 4), window=21)
    assert isinstance(result, pd.Series)
    assert len(result) == 1


def test_compute_information_ratio_sign_when_excess_positive(
    stock_df: pd.DataFrame, bench_df: pd.DataFrame
) -> None:
    """窓内で超過リターンが一定なら情報比率の符号が期待通りであること。"""
    result = compute_information_ratio(stock_df, bench_df, date(2026, 2, 4), window=21)
    valid = result.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()


def test_risk_adjusted_metrics_accept_timezone_aware_index() -> None:
    idx = pd.to_datetime(
        ["2026-01-01 15:00:00+09:00", "2026-01-02 15:00:00+09:00", "2026-01-05 15:00:00+09:00"] * 20,
        utc=True,
    )[:60]
    stock = pd.DataFrame({"Close": [100.0 * (1.01**i) for i in range(len(idx))]}, index=idx)
    bench = pd.DataFrame({"Close": [100.0 * (1.005**i) for i in range(len(idx))]}, index=idx)
    out1 = compute_beta_adjusted_rs(stock, bench, date(2026, 3, 27), beta_window=21, return_window=21)
    out2 = compute_information_ratio(stock, bench, date(2026, 3, 27), window=21)
    assert isinstance(out1, pd.Series) and len(out1) == 1
    assert isinstance(out2, pd.Series) and len(out2) == 1
