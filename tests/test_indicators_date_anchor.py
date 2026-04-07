from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stockradar.indicators.rs import compute_rs


def test_compute_rs_uses_date_anchor_not_row_shift() -> None:
    stock_idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-06", "2026-01-07"])
    stock_df = pd.DataFrame({"Close": [100.0, 102.0, 106.0, 108.0]}, index=stock_idx)
    bench_idx = pd.to_datetime(
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-06", "2026-01-07"]
    )
    bench_df = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=bench_idx)

    out = compute_rs(stock_df, bench_df, windows=[2], run_date=date(2026, 1, 7))
    rs2 = out["rs2"].iloc[0]
    expected = (108.0 / 102.0 - 1.0) - (104.0 / 102.0 - 1.0)
    assert rs2 == pytest.approx(expected, rel=1e-9)
