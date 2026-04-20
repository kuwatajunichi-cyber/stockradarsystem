"""
research_prompt_frame（docs/research_prompt_frame_v1.0.md）の観測データ抜粋ブロックを生成する。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

_RESEARCH_PROMPT_BLOCK_TEMPLATE = """[銘柄の基本情報]
- 観測日: {date}
- 銘柄コード: {code}
- 銘柄名: {name}

[当日の売買代金・値動きの指標]
- 当日の売買代金（概算）: {turnover_yen}円
- 売買代金の異常度（過去60営業日基準のZスコア）: {z_turnover_60}
- 売買代金の平常比（過去60営業日平均に対して何倍か）: {turnover_ma_ratio_60}倍
- 当日騰落率（前営業日終値比）: {price_change_pct}%
- 当日のローソク足形状: {price_text}"""


def _cell_str(row: pd.Series, key: str) -> str:
    if key not in row.index:
        return ""
    v = row[key]
    if pd.isna(v):
        return ""
    return str(v).strip()


def _fmt_yen(v: object) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "（欠損）"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if pd.isna(n):
        return "（欠損）"
    return f"{int(round(n)):,}"


def _fmt_float(v: object, *, ndigits: int = 4) -> str:
    if v is None:
        return "（欠損）"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if pd.isna(f):
        return "（欠損）"
    return str(round(f, ndigits))


def format_research_prompt_block(row: pd.Series) -> str:
    """
    1銘柄分の観測データ抜粋（フレーム v1.0 の該当節）を返す。
    指標列は z_turnover_60 / turnover_ma_ratio_60 を優先し、無い場合は z_turnover_* / turnover_ma_ratio_* の最長サフィックスを用いる。
    """
    date_s = _cell_str(row, "date")
    code_s = _cell_str(row, "code")
    name_s = _cell_str(row, "name")

    z_col = "z_turnover_60"
    if z_col not in row.index or pd.isna(row.get(z_col)):
        z_candidates = [c for c in row.index if str(c).startswith("z_turnover_")]
        z_candidates.sort()
        z_col = z_candidates[-1] if z_candidates else ""

    ratio_col = "turnover_ma_ratio_60"
    if ratio_col not in row.index or pd.isna(row.get(ratio_col)):
        ratio_candidates = [c for c in row.index if str(c).startswith("turnover_ma_ratio_")]
        ratio_candidates.sort()
        ratio_col = ratio_candidates[-1] if ratio_candidates else ""

    z_s = _fmt_float(row[z_col]) if z_col else "（欠損）"
    ratio_s = _fmt_float(row[ratio_col]) if ratio_col else "（欠損）"

    return _RESEARCH_PROMPT_BLOCK_TEMPLATE.format(
        date=date_s or "（欠損）",
        code=code_s or "（欠損）",
        name=name_s or "（欠損）",
        turnover_yen=_fmt_yen(row.get("turnover_yen")),
        z_turnover_60=z_s,
        turnover_ma_ratio_60=ratio_s,
        price_change_pct=_fmt_float(row.get("price_change_pct"), ndigits=4),
        price_text=_cell_str(row, "price_text") or "（欠損）",
    )


def format_research_prompt_block_from_mapping(row: dict[str, Any]) -> str:
    """テスト用: マッピングから Series 相当で生成。"""
    return format_research_prompt_block(pd.Series(row))
