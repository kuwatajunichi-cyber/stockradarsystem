"""run_date 当日バー未到達時に compute が停止することの補助関数テスト。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockradar.jobs.compute_indicators_for_core import max_ohlc_date_on_or_before


def test_max_ohlc_date_on_or_before_filters_run_date() -> None:
    idx = pd.to_datetime(["2026-04-01", "2026-04-02"])
    df = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)
    assert max_ohlc_date_on_or_before(df, date(2026, 4, 2)) == date(2026, 4, 2)
    assert max_ohlc_date_on_or_before(df, date(2026, 4, 1)) == date(2026, 4, 1)


def test_max_ohlc_date_on_or_before_empty_or_none() -> None:
    assert max_ohlc_date_on_or_before(None, date(2026, 4, 2)) is None
    df = pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-04-01"]))
    assert max_ohlc_date_on_or_before(df, date(2026, 3, 1)) is None


def test_max_ohlc_date_detects_stale_vs_run_date() -> None:
    idx = pd.to_datetime(["2026-03-31", "2026-04-01"])
    df = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)
    md = max_ohlc_date_on_or_before(df, date(2026, 4, 2))
    assert md == date(2026, 4, 1)
    assert md < date(2026, 4, 2)
