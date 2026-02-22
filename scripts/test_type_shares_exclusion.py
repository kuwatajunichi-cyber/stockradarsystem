"""
種類株除外ロジックの簡易テスト。
build_universe_from_jpx を実行し、除外された銘柄を示す。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# PYTHONPATH
repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "src"))

import pandas as pd

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


def main() -> None:
    print("=== 入力銘柄と正規化後のコード ===")
    for _, row in MOCK_DATA.iterrows():
        code_raw = row["コード"]
        code_norm = _normalize_code(code_raw)
        excluded = _has_five_or_more_digits(code_norm)
        status = "除外" if excluded else "含む"
        print(f"  {code_raw!r} -> {code_norm!r}  ({status})")

    print()
    base = Path(__file__).parent.parent
    universe_df, messages = build_universe_from_jpx(MOCK_DATA, date.today(), base)

    print("=== メッセージ（WARN等） ===")
    for m in messages.all_messages():
        print(f"  {m}")

    print()
    print("=== ユニバースに含まれた銘柄 ===")
    print(universe_df[["code", "name"]].to_string(index=False))

    # 除外された銘柄を特定
    input_codes = set(MOCK_DATA["コード"].map(_normalize_code)) - {""}
    output_codes = set(universe_df["code"])
    excluded_codes = sorted(input_codes - output_codes)
    print()
    print("=== 除外された銘柄（種類株） ===")
    for c in excluded_codes:
        name = MOCK_DATA[MOCK_DATA["コード"].map(_normalize_code) == c]["銘柄名"].iloc[0]
        print(f"  {c}: {name}")


if __name__ == "__main__":
    main()
