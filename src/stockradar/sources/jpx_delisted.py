"""
JPX 上場廃止銘柄一覧ページをクロールし、廃止銘柄コードを取得する。

- Pure: parse_delisted_table(html, base_url) → (code, date) のリスト
- 取得: fetch_delisted_codes(run_date, lookback_months, fetcher) → 除外対象コードの集合
- パッチ: apply_delisted_patch(universe_df, delisted_codes) → 除外後の DataFrame
"""
from __future__ import annotations

import logging
from datetime import date
import pandas as pd
from bs4 import BeautifulSoup

from stockradar.config import (
    get_jpx_delisted_page_timeout,
    get_jpx_delisted_page_url,
)
from stockradar.sources.jpx_resolver import HttpFetcher

logger = logging.getLogger(__name__)


def _normalize_code(raw: str) -> str:
    """コードを4桁文字列に正規化。数字のみならゼロ埋め、それ以外は strip のみ。"""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return s.zfill(4)
    return s


def _parse_date_cell(text: str) -> date | None:
    """YYYY/MM/DD または YYYY-MM-DD を date に。失敗時は None。"""
    s = (text or "").strip().replace("-", "/")
    if not s or "/" not in s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def parse_delisted_table(html: str, base_url: str) -> list[tuple[str, date]]:
    """
    HTML の表から「コード」「上場廃止日」を抽出する（Pure）。

    表は上場廃止日 | 銘柄名 | コード | 市場区分 | 上場廃止理由 の順を想定。
    base_url は未使用だが将来の相対リンク解決用に受け取る。

    Returns:
        (code, delist_date) のリスト。コードは4桁ゼロ埋め。パース失敗行はスキップ。
    """
    soup = BeautifulSoup(html, "html.parser")
    result: list[tuple[str, date]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            # ヘッダ行は日付がパースできないのでスキップされる
            date_cell = cells[0].get_text(separator=" ", strip=True)
            code_cell = cells[2].get_text(separator=" ", strip=True)
            d = _parse_date_cell(date_cell)
            if d is None:
                continue
            code = _normalize_code(code_cell)
            if not code:
                continue
            result.append((code, d))
    return result


def _cutoff_date_for_lookback(run_date: date, lookback_months: int) -> date:
    """run_date の lookback_months か月前の月初を返す。"""
    year, month = run_date.year, run_date.month
    month -= lookback_months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def fetch_delisted_codes(
    run_date: date,
    lookback_months: int = 2,
    page_url: str | None = None,
    fetcher: HttpFetcher | None = None,
) -> set[str]:
    """
    上場廃止一覧ページを取得し、廃止日が run_date 以前かつ lookback 期間内のコード集合を返す。

    失敗時は空集合で続行し、ログに記録する。fetcher 未指定時は requests で取得。
    """
    import requests

    page_url = page_url or get_jpx_delisted_page_url()
    timeout = get_jpx_delisted_page_timeout()
    cutoff = _cutoff_date_for_lookback(run_date, lookback_months)

    def get_html(url: str) -> str:
        if fetcher is not None:
            return fetcher.get(url)
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    try:
        html = get_html(page_url)
    except Exception as e:
        logger.warning("上場廃止ページの取得に失敗しました: %s — %s", page_url, e)
        return set()

    rows = parse_delisted_table(html, page_url)
    codes = {
        code
        for code, d in rows
        if cutoff <= d <= run_date
    }
    return codes


def apply_delisted_patch(
    universe_df: pd.DataFrame,
    delisted_codes: set[str],
) -> pd.DataFrame:
    """
    universe_df から code が delisted_codes に含まれる行を削除する（Pure）。

    code 列が存在しない場合は ValueError。
    """
    if "code" not in universe_df.columns:
        raise ValueError("universe_df に code 列がありません")
    return universe_df.loc[~universe_df["code"].astype(str).str.strip().isin(delisted_codes)].copy()
