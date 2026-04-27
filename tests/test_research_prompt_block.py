from __future__ import annotations

import json

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
    assert "\n" not in out
    assert "\r" not in out
    d = json.loads(out)
    base = d["銘柄の基本情報"]
    assert base["観測日"] == "2026-03-07"
    assert base["銘柄コード"] == "7203"
    assert base["銘柄名"] == "Toyota"
    m = d["当日の売買代金・値動きの指標"]
    assert m["当日の売買代金（概算）"] == 1234567890
    assert m["売買代金の異常度（過去60営業日基準のZスコア）"] == 2.5
    assert m["売買代金の平常比（過去60営業日平均に対して何倍か）"] == 3.25
    assert m["当日騰落率（前営業日終値比）"] == -1.2345
    assert m["当日のローソク足形状"] == "TEST_CANDLE"
    assert "z_turnover_60" not in out
    assert "turnover_ma_ratio_60" not in out
