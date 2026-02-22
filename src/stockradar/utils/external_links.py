"""
銘柄コードから外部サイトURLを生成する共通モジュール。
externalLink_v1.0.md 準拠。
"""
from __future__ import annotations

from typing import Literal

# canonical キー（docs/externalLink_v1.0.md）と URL テンプレート
_EXTERNAL_LINK_SPEC: dict[str, str] = {
    "kabutan_main": "https://kabutan.jp/stock/?code={code}",
    "kabutan_chart": "https://kabutan.jp/stock/chart?code={code}",
    "kabutan_news": "https://kabutan.jp/stock/news?code={code}",
    "minkabu": "https://minkabu.jp/stock/{code}",
    "buffett": "https://www.buffett-code.com/company/{code}",
    "yahoo": "https://finance.yahoo.co.jp/quote/{code}.T",
}

# canonical -> link_prefix のキー変換（render_sheet.yaml 互換）
_CANONICAL_TO_LINK_PREFIX: dict[str, str] = {
    "kabutan_main": "link_kabutan",
    "kabutan_chart": "link_kabutan_chart",
    "kabutan_news": "link_kabutan_news",
    "minkabu": "link_minkabu",
    "buffett": "link_buffett",
    "yahoo": "link_yahoo",
}


def build_external_links(
    code: str,
    key_format: Literal["canonical", "link_prefix"] = "canonical",
) -> dict[str, str]:
    """
    銘柄コードから外部サイトURLを生成。externalLink_v1.0 準拠。

    Args:
        code: 4桁銘柄コード
        key_format: "canonical" (kabutan_main 等) または "link_prefix" (link_kabutan 等)

    Returns:
        キー -> URL の辞書
    """
    result: dict[str, str] = {}
    for canon_key, url_tpl in _EXTERNAL_LINK_SPEC.items():
        url = url_tpl.format(code=code)
        out_key = _CANONICAL_TO_LINK_PREFIX[canon_key] if key_format == "link_prefix" else canon_key
        result[out_key] = url
    return result
