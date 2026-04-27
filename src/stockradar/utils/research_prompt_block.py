"""
research_prompt_frame（docs/research_prompt_frame_v1.0.md）の観測データ抜粋を
改行なし1行JSON（UTF-8文字列）として返す。
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd


def _cell_str(row: pd.Series, key: str) -> str:
    if key not in row.index:
        return ""
    v = row[key]
    if pd.isna(v):
        return ""
    return str(v).strip()


def _opt_str_or_none(s: str) -> str | None:
    return s if s else None


def _opt_turnover_yen(v: object) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(n):
        return None
    return int(round(n))


def _opt_float(v: object, *, ndigits: int = 4) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return float(round(f, ndigits))


def format_research_prompt_block(row: pd.Series) -> str:
    """
    1銘柄分の観測データ（フレーム v1.0 の [銘柄の基本情報]〜[当日の売買代金・値動きの指標]）を
    改行なしのコンパクトJSONにする。欠損は null。

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

    z_val = _opt_float(row[z_col]) if z_col else None
    ratio_val = _opt_float(row[ratio_col]) if ratio_col else None

    obj: dict[str, Any] = {
        "銘柄の基本情報": {
            "観測日": _opt_str_or_none(date_s),
            "銘柄コード": _opt_str_or_none(code_s),
            "銘柄名": _opt_str_or_none(name_s),
        },
        "当日の売買代金・値動きの指標": {
            "当日の売買代金（概算）": _opt_turnover_yen(row.get("turnover_yen")),
            "売買代金の異常度（過去60営業日基準のZスコア）": z_val,
            "売買代金の平常比（過去60営業日平均に対して何倍か）": ratio_val,
            "当日騰落率（前営業日終値比）": _opt_float(row.get("price_change_pct"), ndigits=4),
            "当日のローソク足形状": _opt_str_or_none(_cell_str(row, "price_text")),
        },
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def format_research_prompt_block_from_mapping(row: dict[str, Any]) -> str:
    """テスト用: マッピングから Series 相当で生成。"""
    return format_research_prompt_block(pd.Series(row))
