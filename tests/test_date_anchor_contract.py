from __future__ import annotations

import pandas as pd

from stockradar.indicators.date_anchor import (
    asof_value,
    build_anchor_context,
    nth_business_anchor,
    prepare_asof_series,
)


def test_nth_business_anchor_uses_unique_sorted_dates() -> None:
    idx = pd.to_datetime(["2026-01-03", "2026-01-02", "2026-01-02", "2026-01-06"])
    ctx = build_anchor_context(idx)
    anchor = pd.Timestamp("2026-01-06")
    assert nth_business_anchor(ctx, anchor, 0) == pd.Timestamp("2026-01-06")
    assert nth_business_anchor(ctx, anchor, 1) == pd.Timestamp("2026-01-03")
    assert nth_business_anchor(ctx, anchor, 2) == pd.Timestamp("2026-01-02")


def test_asof_value_uses_dropna_sort_and_latest_before_anchor() -> None:
    s = pd.Series(
        [None, 10.0, 11.0],
        index=pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-05"]),
    )
    prepared = prepare_asof_series(s)
    assert asof_value(prepared, pd.Timestamp("2026-01-04")) == 10.0
    assert asof_value(prepared, pd.Timestamp("2026-01-05")) == 11.0
