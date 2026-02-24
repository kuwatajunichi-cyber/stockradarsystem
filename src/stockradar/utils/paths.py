"""
パス探索・CSV読み込み・ティッカー変換などの共通ユーティリティ。
パス定数（get_universe_jpx_dir, get_processed_jpx_dir）は config に集約し、ここで re-export。
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from stockradar.config import get_processed_jpx_dir, get_universe_jpx_dir

# config から re-export（後方互換）
__all__ = [
    "PATTERN_SETS",
    "PATTERN_SETS_SECONDARY",
    "ticker_for_code",
    "load_codes_from_csv",
    "find_latest_matching",
    "get_universe_jpx_dir",
    "get_processed_jpx_dir",
    "find_latest_processed_jpx",
]

# ディレクトリパターン定数
PATTERN_SETS = r"sets_\d{8}"
PATTERN_SETS_SECONDARY = r"sets_secondary_\d{8}"


def ticker_for_code(code: str) -> str:
    """日本株の Yahoo ティッカー（例: 7203 -> 7203.T）を返す。"""
    return f"{code}.T"


def load_codes_from_csv(path: Path) -> list[str]:
    """
    CSV から code 列を読み込み、銘柄コードのリストを返す。

    Raises:
        ValueError: code 列が存在しない場合
    """
    df = pd.read_csv(path)
    if "code" not in df.columns:
        raise ValueError(f"入力CSVに code 列がありません: {path}")
    return [str(c).strip() for c in df["code"].dropna() if str(c).strip()]


def find_latest_matching(
    base_dir: Path,
    dir_pattern: str,
    filename: str,
) -> Path | None:
    """
    ベースディレクトリ配下で、パターンに合うディレクトリ内の filename の最新パスを返す。

    Args:
        base_dir: 検索の起点（例: data/universe/jpx）
        dir_pattern: ディレクトリ名の正規表現（例: r"sets_\d{8}"）
        filename: 探すファイル名（例: equity_domestic.csv）

    Returns:
        見つかった最新のファイルパス、または None
    """
    if not base_dir.exists():
        return None
    pattern = re.compile(dir_pattern)
    candidates: list[Path] = []
    for d in base_dir.iterdir():
        if d.is_dir() and pattern.match(d.name):
            p = d / filename
            if p.exists():
                candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name)
    return candidates[-1]


def find_latest_processed_jpx(base_dir: Path) -> Path | None:
    """
    data/processed/jpx/jpx_list_*.csv の最新ファイルを返す。
    """
    processed_dir = get_processed_jpx_dir(base_dir)
    if not processed_dir.exists():
        return None
    candidates = sorted(processed_dir.glob("jpx_list_*.csv"))
    if not candidates:
        return None
    return candidates[-1]
