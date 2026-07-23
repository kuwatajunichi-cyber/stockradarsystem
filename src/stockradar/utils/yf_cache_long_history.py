"""Long-history yfinance fetch for Layer 1 backfill PoC (Phase 4.5).

Daily pipeline default paths in yf_cache.py are unchanged; this module is PoC-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

import pandas as pd

DEFAULT_CHUNK_CALENDAR_DAYS = 400


def iter_start_end_chunks(
    *,
    end: datetime,
    total_calendar_days: int,
    chunk_calendar_days: int = DEFAULT_CHUNK_CALENDAR_DAYS,
) -> list[tuple[datetime, datetime]]:
    """Split [end - total_calendar_days, end] into overlapping chunks (1-day overlap)."""
    if chunk_calendar_days <= 1:
        raise ValueError("chunk_calendar_days must be > 1")
    start = end - timedelta(days=total_calendar_days)
    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_calendar_days), end)
        chunks.append((cursor, chunk_end))
        if chunk_end >= end:
            break
        cursor = chunk_end - timedelta(days=1)
    return chunks


def merge_ohlc_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Merge chunk frames: sort index, dedupe, keep required OHLCV columns."""
    parts = [f for f in frames if f is not None and not f.empty]
    if not parts:
        return pd.DataFrame()
    merged = pd.concat(parts).sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged


def calendar_days_for_trading_days(trading_days: int) -> int:
    """Approximate calendar days to cover trading_days (7/5 ratio + buffer)."""
    return int(trading_days * 7 / 5) + 30


FetchChunkFn = Callable[[datetime, datetime], pd.DataFrame]


def fetch_long_history(
    *,
    end: datetime | None = None,
    required_trading_days: int,
    fetch_chunk: FetchChunkFn,
    chunk_calendar_days: int = DEFAULT_CHUNK_CALENDAR_DAYS,
) -> pd.DataFrame:
    """
    Fetch required_trading_days via chunked start/end calls.

    fetch_chunk: injected Fake or yfinance wrapper (Secrets-free tests use Fake).
    """
    end_dt = end or datetime.now(timezone.utc)
    total_cal = calendar_days_for_trading_days(required_trading_days)
    frames = [fetch_chunk(start, chunk_end) for start, chunk_end in iter_start_end_chunks(
        end=end_dt,
        total_calendar_days=total_cal,
        chunk_calendar_days=chunk_calendar_days,
    )]
    return merge_ohlc_frames(frames)


def classify_history_eligibility(
    n_bars: int,
    *,
    required_trading_days: int,
    listing_age_trading_days: int | None = None,
) -> str:
    """eligible | expected_short_history | insufficient."""
    if listing_age_trading_days is not None and listing_age_trading_days < required_trading_days:
        return "expected_short_history"
    if n_bars >= required_trading_days:
        return "eligible"
    return "insufficient"
