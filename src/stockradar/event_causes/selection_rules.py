"""
ニュース収集対象銘柄の抽出条件（selection_rules）評価。

I/O 非依存で、DataFrame の行データのみから判定できる Pure ロジックを提供する。
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def default_selection_rules(z_column: str = "z_turnover_60", z_threshold: float = 3.5) -> dict[str, Any]:
    """後方互換用の既定抽出条件を返す。"""
    return {
        "any_of": [
            {
                "type": "z_turnover_gt",
                "column": z_column,
                "value": float(z_threshold),
            }
        ]
    }


def resolve_selection_rules(
    selection_rules: dict[str, Any] | None,
    *,
    z_column: str,
    z_threshold: float,
) -> dict[str, Any]:
    """
    selection_rules が未指定なら、z_column/z_threshold から既定条件を構築する。
    """
    if isinstance(selection_rules, dict) and selection_rules.get("any_of"):
        return selection_rules
    return default_selection_rules(z_column=z_column, z_threshold=z_threshold)


def _to_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_label_tokens(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [x.strip().upper() for x in text.split(",") if x.strip()]


def evaluate_rule(row: pd.Series, rule: dict[str, Any]) -> bool:
    """
    単一ルールを評価する。

    Supported types:
      - z_turnover_gt
      - z_turnover_lt
      - candle_labels_contains_any
    """
    rule_type = str(rule.get("type", "")).strip().lower()
    if not rule_type:
        return False

    if rule_type in {"z_turnover_gt", "z_turnover_lt"}:
        col = str(rule.get("column", "")).strip()
        threshold = _to_float(rule.get("value"))
        if not col or threshold is None or col not in row.index:
            return False
        cur = _to_float(row.get(col))
        if cur is None:
            return False
        if rule_type == "z_turnover_gt":
            return cur > threshold
        return cur < threshold

    if rule_type == "candle_labels_contains_any":
        col = str(rule.get("column", "candle_labels")).strip() or "candle_labels"
        if col not in row.index:
            return False
        targets = [str(x).strip().upper() for x in (rule.get("values") or []) if str(x).strip()]
        if not targets:
            return False
        row_tokens = _normalize_label_tokens(row.get(col))
        if not row_tokens:
            return False
        return any(any(token.startswith(t) for token in row_tokens) for t in targets)

    return False


def evaluate_any_of(row: pd.Series, selection_rules: dict[str, Any]) -> bool:
    rules = selection_rules.get("any_of", [])
    if not isinstance(rules, list) or not rules:
        return False
    for rule in rules:
        if isinstance(rule, dict) and evaluate_rule(row, rule):
            return True
    return False


def filter_dataframe(df: pd.DataFrame, selection_rules: dict[str, Any]) -> pd.DataFrame:
    """
    selection_rules.any_of を満たす行を返す。
    """
    if df.empty:
        return df.copy()
    mask = df.apply(lambda r: evaluate_any_of(r, selection_rules), axis=1)
    return df[mask].copy()

