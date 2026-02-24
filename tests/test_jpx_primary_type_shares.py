"""
種類株除外ロジックのテスト。
build_universe_from_jpx および _normalize_code / _has_five_or_more_digits を検証する。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

import pytest

from stockradar.universe.jpx_primary import (
    _has_five_or_more_digits,
    _normalize_code,
    build_universe_from_jpx,
)

# モック: 通常銘柄(4桁) + 種類株(5桁) のサンプル
MOCK_DATA = pd.DataFrame({
    "コード": ["7203", "9984", "8035", 10001, 10002, "12345", 8765, "1234"],
    "銘柄名": [
        "トヨタ自動車",
        "ソフトバンクG",
        "東京建物",
        "種類株A",
        "種類株B",
        "種類株C",
        "通常株",
        "通常株2",
    ],
    "市場・商品区分": ["内国株式"] * 8,
})


def test_normalize_code_and_type_shares_exclusion() -> None:
    """正規化と種類株（5桁以上）除外判定を検証する。"""
    expectations = [
        ("7203", "7203", False),
        ("9984", "9984", False),
        ("8035", "8035", False),
        (10001, "10001", True),
        (10002, "10002", True),
        ("12345", "12345", True),
        (8765, "8765", False),
        ("1234", "1234", False),
    ]
    for code_raw, expected_norm, expected_excluded in expectations:
        code_norm = _normalize_code(code_raw)
        assert code_norm == expected_norm
        assert _has_five_or_more_digits(code_norm) is expected_excluded


def test_build_universe_from_jpx_excludes_type_shares(tmp_path: Path) -> None:
    """build_universe_from_jpx が種類株を除外し、通常銘柄のみ含むことを検証する。"""
    base_dir = tmp_path
    universe_df, messages = build_universe_from_jpx(MOCK_DATA, date.today(), base_dir)

    input_codes = set(MOCK_DATA["コード"].map(_normalize_code)) - {""}
    output_codes = set(universe_df["code"])
    excluded_codes = sorted(input_codes - output_codes)

    # 種類株（5桁）は除外される
    assert excluded_codes == ["10001", "10002", "12345"]
    # 通常銘柄は含まれる
    assert "7203" in output_codes
    assert "9984" in output_codes
    assert "8035" in output_codes
    assert "8765" in output_codes
    assert "1234" in output_codes

    # WARN に種類株除外が含まれる
    msg_list = list(messages.all_messages())
    assert any("TYPE_SHARES_EXCLUDED" in m for m in msg_list)

    # 出力スキーマ
    assert list(universe_df.columns) == [
        "date",
        "code",
        "name",
        "market_product_raw",
        "universe_primary",
    ]
