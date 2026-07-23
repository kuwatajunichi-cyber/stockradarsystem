"""Layer 1 retention contract (Phase 4.5 Blocker 1)."""
from __future__ import annotations

import pytest

from stockradar.config import compute_layer1_required_trading_days, compute_layer1_retention_trading_days
from stockradar.jobs import archive_ohlc_store
from stockradar.jobs.layer1_retention import prune_index_by_trading_days, trading_day_cutoff_date
from stockradar.utils.yf_cache_long_history import (
    calendar_days_for_trading_days,
    classify_history_eligibility,
    fetch_long_history,
    iter_start_end_chunks,
    merge_ohlc_frames,
)

pytestmark = pytest.mark.unit


def test_required_trading_days_is_at_least_772() -> None:
    assert compute_layer1_required_trading_days() >= 772


def test_retention_at_least_required() -> None:
    assert compute_layer1_retention_trading_days() >= compute_layer1_required_trading_days()


def test_production_retention_days_unchanged() -> None:
    assert archive_ohlc_store.RETENTION_DAYS == 730


def test_merge_dedupes_overlapping_chunks() -> None:
    import pandas as pd

    idx = pd.bdate_range("2024-01-01", periods=5)
    df1 = pd.DataFrame({"Close": [1, 2, 3]}, index=idx[:3])
    df2 = pd.DataFrame({"Close": [3, 4, 5]}, index=idx[2:])
    merged = merge_ohlc_frames([df1, df2])
    assert not merged.index.duplicated().any()
    assert len(merged) == 5


def test_fetch_long_history_fake_meets_required() -> None:
    import pandas as pd

    required = 772

    def fake_chunk(start, end):
        idx = pd.bdate_range(end=end.date(), periods=800)
        return pd.DataFrame(
            {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1},
            index=idx,
        )

    df = fetch_long_history(required_trading_days=required, fetch_chunk=fake_chunk)
    assert len(df) >= required


def test_classify_expected_short_history() -> None:
    assert (
        classify_history_eligibility(100, required_trading_days=772, listing_age_trading_days=200)
        == "expected_short_history"
    )


def test_iter_chunks_covers_range() -> None:
    from datetime import datetime, timezone

    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chunks = iter_start_end_chunks(end=end, total_calendar_days=800, chunk_calendar_days=400)
    assert len(chunks) >= 2


def test_trading_day_prune_pure() -> None:
    from datetime import date

    cutoff = trading_day_cutoff_date(date(2026, 7, 1), retention_trading_days=252)
    kept = prune_index_by_trading_days(
        [date(2025, 1, 1), date(2026, 6, 1), date(2026, 7, 1)],
        cutoff=cutoff,
    )
    assert date(2025, 1, 1) not in kept


def test_calendar_days_for_trading_days() -> None:
    assert calendar_days_for_trading_days(772) > 772
