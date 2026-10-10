"""
窓ラベル（GAP_UP / GAP_DOWN）は酒田・チャート用語に合わせる。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from stockradar.utils.candle_descriptor import compute_candle_descriptors

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _two_day_ohlc(
    prev: tuple[float, float, float, float],
    today: tuple[float, float, float, float],
) -> pd.DataFrame:
    dates = pd.DatetimeIndex(["2026-03-05", "2026-03-06"], name="date")
    return pd.DataFrame(
        {
            "Open": [prev[0], today[0]],
            "High": [prev[1], today[1]],
            "Low": [prev[2], today[2]],
            "Close": [prev[3], today[3]],
        },
        index=dates,
    )


def test_gap_up_when_today_range_is_entirely_above_prev() -> None:
    """前日高 < 当日安 → 上窓（GAP_UP）。"""
    df = _two_day_ohlc((99.0, 100.0, 98.0, 99.0), (102.0, 103.0, 101.0, 102.0))
    labels, price_text = compute_candle_descriptors(df)
    assert "GAP_UP" in labels.split(",")
    assert "GAP_DOWN" not in labels.split(",")
    assert price_text.startswith("上窓＋")


def test_gap_down_when_today_range_is_entirely_below_prev() -> None:
    """前日安 > 当日高 → 下窓（GAP_DOWN）。"""
    df = _two_day_ohlc((99.0, 100.0, 98.0, 99.0), (96.0, 97.0, 95.0, 96.0))
    labels, price_text = compute_candle_descriptors(df)
    assert "GAP_DOWN" in labels.split(",")
    assert "GAP_UP" not in labels.split(",")
    assert price_text.startswith("下窓＋")


def test_no_window_when_ranges_overlap() -> None:
    df = _two_day_ohlc((99.0, 100.0, 98.0, 99.0), (99.0, 101.0, 97.0, 100.0))
    labels, _price_text = compute_candle_descriptors(df)
    tokens = labels.split(",") if labels else []
    assert "GAP_UP" not in tokens
    assert "GAP_DOWN" not in tokens


def test_ohlc_ssot_gap_table_matches_sakata() -> None:
    text = (REPO_ROOT / "docs" / "OHLC_desripter_v1.3.md").read_text(encoding="utf-8")
    assert "| `GAP_UP`   | `前日の最高値 < 当日の最低値` | 上窓＋ |" in text
    assert "| `GAP_DOWN` | `前日の最低値 > 当日の最高値` | 下窓＋ |" in text
