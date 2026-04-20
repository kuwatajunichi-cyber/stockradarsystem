"""
出来高zscore（compute_zscore_turnover）のテスト。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stockradar.indicators.zscore import compute_turnover_ma_ratio_from_prepared, compute_zscore_turnover


@pytest.fixture
def df_with_close_volume() -> pd.DataFrame:
    """Close と Volume を持つ DataFrame（5〜10行、日付 index）。"""
    dates = pd.DatetimeIndex(
        pd.date_range("2026-01-01", periods=8, freq="B"),
        name="date",
    )
    # 一定の売買代金にしやすいよう Close=100, Volume=1000 で固定
    return pd.DataFrame(
        {"Close": [100.0] * 8, "Volume": [1000.0] * 8},
        index=dates,
    )


def test_compute_zscore_turnover_returns_series(
    df_with_close_volume: pd.DataFrame,
) -> None:
    """戻りが run_date アンカー1点 Series であること。"""
    result = compute_zscore_turnover(
        df_with_close_volume,
        lookback_days=21,
        run_date=date(2026, 1, 12),
    )
    assert isinstance(result, pd.Series)
    assert len(result) == 1


def test_compute_zscore_turnover_leading_nan_with_small_lookback(
    df_with_close_volume: pd.DataFrame,
) -> None:
    """窓不足で先頭が NaN になること。"""
    result = compute_zscore_turnover(
        df_with_close_volume,
        lookback_days=21,
        run_date=date(2026, 1, 12),
    )
    assert pd.isna(result.iloc[0])


def test_compute_zscore_turnover_with_timezone_aware_index() -> None:
    idx = pd.to_datetime(
        ["2026-01-01 15:00:00+09:00", "2026-01-02 15:00:00+09:00", "2026-01-05 15:00:00+09:00"],
        utc=True,
    )
    df = pd.DataFrame(
        {"Close": [100.0, 101.0, 102.0], "Volume": [1000.0, 1100.0, 1200.0]},
        index=idx,
    )
    out = compute_zscore_turnover(df, lookback_days=2, run_date=date(2026, 1, 5))
    assert isinstance(out, pd.Series)
    assert len(out) == 1


def test_compute_turnover_ma_ratio_flat_window_is_one() -> None:
    """売買代金が一定なら、平均に対する倍率は 1（窓内がすべて同一売買代金）。"""
    dates = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=30, freq="B"), name="date")
    df = pd.DataFrame({"Close": [100.0] * 30, "Volume": [1000.0] * 30}, index=dates)
    run_date = pd.Timestamp(dates.max()).date()
    result = compute_turnover_ma_ratio_from_prepared(df, lookback_days=21, run_date=run_date)
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(1.0)


def test_zscore_turnover_requires_non_null_turnover_count_not_only_row_count() -> None:
    """行数が足りても売買代金が有効な本数が min_periods 未満なら欠損。"""
    dates = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=25, freq="B"), name="date")
    close = [float("nan")] * 24 + [100.0]
    vol = [1000.0] * 25
    df = pd.DataFrame({"Close": close, "Volume": vol}, index=dates)
    run_date = pd.Timestamp(dates.max()).date()
    result = compute_zscore_turnover(df, lookback_days=21, run_date=run_date)
    assert pd.isna(result.iloc[0])


def test_turnover_ma_ratio_requires_non_null_turnover_count() -> None:
    """倍率も有効な売買代金本数で min_periods を判定する。"""
    dates = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=25, freq="B"), name="date")
    close = [float("nan")] * 24 + [100.0]
    vol = [1000.0] * 25
    df = pd.DataFrame({"Close": close, "Volume": vol}, index=dates)
    run_date = pd.Timestamp(dates.max()).date()
    result = compute_turnover_ma_ratio_from_prepared(df, lookback_days=21, run_date=run_date)
    assert pd.isna(result.iloc[0])


def test_compute_turnover_ma_ratio_spike_last_bar() -> None:
    """最終バーだけ売買代金が高いと倍率が 1 を超える。"""
    dates = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=25, freq="B"), name="date")
    close = [100.0] * 25
    vol = [1000.0] * 24 + [3000.0]
    df = pd.DataFrame({"Close": close, "Volume": vol}, index=dates)
    run_date = pd.Timestamp(dates.max()).date()
    result = compute_turnover_ma_ratio_from_prepared(df, lookback_days=21, run_date=run_date)
    assert len(result) == 1
    assert result.iloc[0] is not None
    assert float(result.iloc[0]) > 1.0
