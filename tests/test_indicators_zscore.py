"""
出来高zscore（compute_zscore_turnover）のテスト。
"""
from __future__ import annotations

import pandas as pd
import pytest

from stockradar.indicators.zscore import compute_zscore_turnover


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
    """戻りが Series で index が入力と同一であること。"""
    # min_periods = max(20, int(lookback_days*0.7)) のため lookback_days >= 21 が必要
    result = compute_zscore_turnover(df_with_close_volume, lookback_days=21)
    assert isinstance(result, pd.Series)
    assert result.index.equals(df_with_close_volume.index)


def test_compute_zscore_turnover_leading_nan_with_small_lookback(
    df_with_close_volume: pd.DataFrame,
) -> None:
    """窓不足で先頭が NaN になること。"""
    # lookback_days=21 でも 8 行しかないため min_periods=20 に満たず先頭は NaN
    result = compute_zscore_turnover(df_with_close_volume, lookback_days=21)
    assert pd.isna(result.iloc[0])
