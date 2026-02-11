"""
JPX 銘柄一覧（一次ソース）から一次ユニバースを構成するためのロジック。

- 「市場・商品区分」に基づき universe_primary を 6分類 + unknown にマッピング
- 「市場・商品区分」列の欠損やカテゴリ集合の変化を UNIVERSE_SCHEMA アラートとして検出
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import json
import math

import pandas as pd

from stockradar.config import get_jpx_market_product_categories_cache_path


UNIVERSE_IDS = [
    "equity_domestic",
    "equity_foreign",
    "etf_etn",
    "reit_funds",
    "pro_market",
    "investment_securities",
    "unknown",
]


@dataclass
class UniverseMessages:
    """ジョブ向けのメッセージ集。"""

    alerts: list[str]
    warns: list[str]

    def all_messages(self) -> Iterable[str]:
        yield from self.alerts
        yield from self.warns


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _normalize_code(value: object) -> str:
    """
    コードを4桁文字列に正規化する。
    - 数値 1234 / 1234.0 → "1234"
    - 文字列 "1234" / "0123" → ゼロ埋め維持 or 4桁ゼロ埋め
    - 欠損 / 不明 → ""
    """
    if value is None or _is_nan(value):
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # 小数表現 "1234.0" を整数化
    if s.replace(".", "", 1).isdigit():
        try:
            num = int(float(s))
            return f"{num:04d}"
        except ValueError:
            pass
    # 数字のみの文字列
    if s.isdigit():
        return s.zfill(4)
    return s


def _normalize_str(value: object) -> str:
    if value is None or _is_nan(value):
        return ""
    return str(value).strip()


def assign_universe_primary(market_product_raw: str) -> str:
    """市場・商品区分の文字列から universe_primary を決定する。"""
    text = (market_product_raw or "").strip()
    if not text:
        return "unknown"

    # マッピング仕様に忠実に実装
    if "内国株式" in text:
        return "equity_domestic"
    if "外国株式" in text:
        return "equity_foreign"
    if text == "ETF・ETN":
        return "etf_etn"
    if text == "REIT・ベンチャーファンド・カントリーファンド・インフラファンド":
        return "reit_funds"
    if "PRO Market" in text or "TOKYO PRO Market" in text:
        return "pro_market"
    if text == "出資証券":
        return "investment_securities"
    return "unknown"


def _load_category_cache(path: Path) -> set[str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "categories" in data and isinstance(
            data["categories"], list
        ):
            return {str(v) for v in data["categories"]}
        if isinstance(data, list):
            return {str(v) for v in data}
    except Exception:
        return None
    return None


def _save_category_cache(path: Path, categories: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"categories": sorted(categories)}
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def build_universe_from_jpx(
    df: pd.DataFrame,
    as_of_date: date,
    base_dir: Path,
) -> tuple[pd.DataFrame, UniverseMessages]:
    """
    JPX processed CSV から一次ユニバースを構築する。

    戻り値:
        universe_df: columns = [date, code, name, market_product_raw, universe_primary]
        messages: UNIVERSE_SCHEMA アラートおよび WARN 群
    """
    alerts: list[str] = []
    warns: list[str] = []

    # 列名
    col_code = "コード"
    col_name = "銘柄名"
    col_market = "市場・商品区分"

    # 必須列チェック（コード・銘柄名）: 無い場合は即エラーとする
    missing_essential = [c for c in (col_code, col_name) if c not in df.columns]
    if missing_essential:
        raise ValueError(f"入力CSVに必須列がありません: {missing_essential}")

    # コード正規化 & 重複チェック
    codes = df[col_code].map(_normalize_code)
    df_normalized = pd.DataFrame()
    df_normalized["code"] = codes
    df_normalized["name"] = df[col_name].map(_normalize_str)

    # コード欠損 WARN
    missing_code_count = (df_normalized["code"] == "").sum()
    if missing_code_count:
        warns.append(
            f"WARN[UNIVERSE_SCHEMA]: CODE_MISSING count={missing_code_count}"
        )

    # 銘柄名欠損 WARN
    missing_name_count = (df_normalized["name"] == "").sum()
    if missing_name_count:
        warns.append(
            f"WARN[UNIVERSE_SCHEMA]: NAME_MISSING count={missing_name_count}"
        )

    # コード重複はエラー（空コードは除外）
    non_empty_codes = df_normalized["code"][df_normalized["code"] != ""]
    dup_codes = non_empty_codes[non_empty_codes.duplicated()].unique()
    if len(dup_codes) > 0:
        raise ValueError(
            f"コードが重複しています: {', '.join(sorted(dup_codes))}"
        )

    # 市場・商品区分の有無とカテゴリ集合チェック
    market_missing = col_market not in df.columns
    cache_path = get_jpx_market_product_categories_cache_path(base_dir)

    if market_missing:
        alerts.append("ALERT[UNIVERSE_SCHEMA]: COLUMN_MISSING market_product")
        df_normalized["market_product_raw"] = ""
        df_normalized["universe_primary"] = "unknown"
    else:
        raw_market = df[col_market].map(_normalize_str)
        df_normalized["market_product_raw"] = raw_market

        current_categories: set[str] = {v for v in raw_market.unique() if v}
        cached = _load_category_cache(cache_path)

        if cached is None and current_categories:
            # 初回: 基準作成
            _save_category_cache(cache_path, current_categories)
        elif cached is not None:
            if current_categories != cached:
                added = sorted(current_categories - cached)
                removed = sorted(cached - current_categories)
                alerts.append(
                    "ALERT[UNIVERSE_SCHEMA]: CATEGORY_SET_CHANGED "
                    f"added={added} removed={removed}"
                )
                # 成功時のみキャッシュ更新: 呼び出し側でエラーにならなかった前提で更新される
                _save_category_cache(cache_path, current_categories)

        # マッピング本体
        df_normalized["universe_primary"] = raw_market.map(assign_universe_primary)

    # 日付列を追加
    df_normalized["date"] = as_of_date.isoformat()

    # 列順を揃える
    universe_df = df_normalized[
        ["date", "code", "name", "market_product_raw", "universe_primary"]
    ].copy()

    return universe_df, UniverseMessages(alerts=alerts, warns=warns)

