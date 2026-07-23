"""Pure trading-day retention helpers for Layer 1 archive (Phase 4.5)."""
from __future__ import annotations

from datetime import date

from stockradar.utils.yf_cache_long_history import calendar_days_for_trading_days


def trading_day_cutoff_date(
    run_date: date,
    *,
    retention_trading_days: int,
) -> date:
    """
    run_date を含む直近 retention_trading_days 営業日の最古 cutoff 日（暦日近似）。

    PoC/契約用: JPX 式暦日換算（245 sessions/year + buffer）を使う。
    """
    if retention_trading_days <= 0:
        raise ValueError("retention_trading_days must be positive")
    calendar_days = calendar_days_for_trading_days(retention_trading_days)
    return run_date.fromordinal(run_date.toordinal() - calendar_days)


def prune_index_by_trading_days(
    index_dates: list[date],
    *,
    cutoff: date,
) -> list[date]:
    """cutoff 以降の index 日付だけ残す（pure）。"""
    return [d for d in index_dates if d >= cutoff]
