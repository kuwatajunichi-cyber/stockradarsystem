"""Shared XTKS trading-day axis for the as-of Web UI prototype."""
from __future__ import annotations

from datetime import date, timedelta

import exchange_calendars as xcals

from stockradar.prototype_web_ui_asof import AXIS_LEN


def xtks_axis_dates(as_of: date, *, n: int = AXIS_LEN) -> list[date]:
    """Return the last ``n`` XTKS sessions on or before ``as_of`` (ascending)."""
    if n <= 0:
        raise ValueError("n must be positive")
    cal = xcals.get_calendar("XTKS")
    start = as_of - timedelta(days=max(n * 3, 120))
    sessions = cal.sessions_in_range(str(start), str(as_of))
    dates = [ts.date() for ts in sessions if ts.date() <= as_of]
    if len(dates) < n:
        raise ValueError(
            f"XTKS axis needs {n} sessions on/before {as_of.isoformat()}, got {len(dates)}"
        )
    return dates[-n:]


def require_index_asof_bar(index_dates: set[date], as_of: date, *, label: str) -> None:
    """Fail closed when an index cache lacks the as-of session."""
    if as_of not in index_dates:
        raise ValueError(
            f"index cache {label!r} missing as-of bar {as_of.isoformat()} "
            f"(cache_max={max(index_dates) if index_dates else None})"
        )
