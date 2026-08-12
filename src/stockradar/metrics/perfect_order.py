"""Perfect Order days metric (Phase 4.5 v1 — halt out of scope)."""
from __future__ import annotations

from datetime import date

import pandas as pd

PERFECT_ORDER_MIN_HISTORY_DAYS = 220
SMA_WINDOWS = (25, 75, 200)


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def compute_perfect_order_days(
    close: pd.Series,
    *,
    run_date: date,
    min_history_days: int = PERFECT_ORDER_MIN_HISTORY_DAYS,
) -> int | None:
    """
    Count consecutive trading days (ending at run_date) where SMA25 > SMA75 > SMA200.

    Returns None when history is insufficient or run_date bar is missing.
    Trading halt is out of scope for v1 — only missing bars / insufficient history
    produce null.
    """
    if close.empty:
        return None
    sub = close[close.index.date <= run_date]
    if sub.empty or len(sub) < min_history_days:
        return None
    if pd.Timestamp(sub.index.max()).date() < run_date:
        return None
    sma25 = _sma(sub, SMA_WINDOWS[0])
    sma75 = _sma(sub, SMA_WINDOWS[1])
    sma200 = _sma(sub, SMA_WINDOWS[2])
    ordered = (sma25 > sma75) & (sma75 > sma200)
    if ordered.isna().all():
        return None
    count = 0
    for val in reversed(ordered.tolist()):
        if val is True:
            count += 1
        elif val is False:
            break
        else:
            break
    return count if count > 0 else 0
