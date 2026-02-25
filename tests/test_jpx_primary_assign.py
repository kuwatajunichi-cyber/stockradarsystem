"""
assign_universe_primary のテスト。
市場・商品区分文字列から universe_primary へのマッピングを検証する。
"""
from __future__ import annotations

import pytest

from stockradar.universe.jpx_primary import assign_universe_primary


@pytest.mark.parametrize(
    "market_product_raw,expected",
    [
        ("内国株式", "equity_domestic"),
        ("外国株式", "equity_foreign"),
        ("ETF・ETN", "etf_etn"),
        ("REIT・ベンチャーファンド・カントリーファンド・インフラファンド", "reit_funds"),
        ("PRO Market", "pro_market"),
        ("TOKYO PRO Market", "pro_market"),
        ("その他 PRO Market 付き", "pro_market"),
        ("出資証券", "investment_securities"),
        ("", "unknown"),
        ("   ", "unknown"),
        ("未知のカテゴリ", "unknown"),
    ],
)
def test_assign_universe_primary(market_product_raw: str, expected: str) -> None:
    """市場・商品区分から universe_primary が仕様どおりマッピングされること。"""
    assert assign_universe_primary(market_product_raw) == expected


def test_assign_universe_primary_none_treated_as_unknown() -> None:
    """None が空として扱われ unknown になること（実装の or "" の挙動）。"""
    # 型上は str だが実装が (market_product_raw or "").strip() のため None で動作する
    result = assign_universe_primary(None)  # type: ignore[arg-type]
    assert result == "unknown"
