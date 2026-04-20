from __future__ import annotations

import pandas as pd

from stockradar.utils.research_prompt_block import format_research_prompt_block


def test_format_research_prompt_block_substitutes_frame() -> None:
    row = pd.Series(
        {
            "date": "2026-03-07",
            "code": "7203",
            "name": "Toyota",
            "turnover_yen": 1234567890.4,
            "z_turnover_60": 2.5,
            "turnover_ma_ratio_60": 3.25,
            "price_change_pct": -1.2345,
            "price_text": "TEST_CANDLE",
        }
    )
    out = format_research_prompt_block(row)
    assert "7203" in out
    assert "Toyota" in out
    assert "1,234,567,890" in out
    assert "2.5" in out
    assert "3.25" in out
    assert "-1.2345" in out
    assert "TEST_CANDLE" in out
    assert "z_turnover_60" not in out
    assert "turnover_ma_ratio_60" not in out
