"""
JPX 銘柄一覧ページから最新の Excel（.xls / .xlsx）URL を抽出し、
キャッシュ更新とフォールバックを行う。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from stockradar.config import get_jpx_cache_path, get_jpx_page_url, get_jpx_page_timeout

logger = logging.getLogger(__name__)


class HttpFetcher(Protocol):
    """HTTP でページ本文を取得する抽象。"""

    def get(self, url: str) -> str:
        """指定 URL のレスポンス本文を返す。失敗時は例外。"""
        ...


def extract_excel_urls_from_html(html: str, base_url: str) -> list[str]:
    """
    HTML 文字列から同一サイト内の .xls / .xlsx リンクの絶対 URL を抽出する（Pure）。

    Args:
        html: ページの HTML 文字列
        base_url: 相対パス解決の基準 URL

    Returns:
        絶対 URL のリスト（見つからなければ空リスト）
    """
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc
    result: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith((".xls", ".xlsx")):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc == base_netloc:
            result.append(absolute)
    return result


def resolve_latest_url(
    page_url: str,
    *,
    fetcher: HttpFetcher | None = None,
) -> str | None:
    """
    固定ページの HTML から銘柄一覧 Excel のダウンロードURLを抽出する。
    成功時は絶対URLを返し（先頭1件）、見つからない・取得失敗時は None。

    fetcher 未指定時は requests で取得する。
    """
    if fetcher is None:
        try:
            resp = requests.get(page_url, timeout=get_jpx_page_timeout())
            resp.raise_for_status()
            html = resp.text
            base_url = resp.url
        except requests.RequestException:
            return None
    else:
        try:
            html = fetcher.get(page_url)
            base_url = page_url
        except Exception:
            return None

    urls = extract_excel_urls_from_html(html, base_url)
    return urls[0] if urls else None


def read_cache(cache_path: Path) -> str | None:
    """キャッシュファイルから URL を読み取る。無い・空の場合は None。"""
    if not cache_path.exists():
        return None
    try:
        url = cache_path.read_text(encoding="utf-8").strip()
        return url or None
    except OSError:
        return None


def write_cache(cache_path: Path, url: str) -> None:
    """キャッシュファイルに URL を書き込む。"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(url, encoding="utf-8")


def resolve_and_update_cache(
    base_dir: Path,
    page_url: str | None = None,
    cache_path: Path | None = None,
) -> str:
    """
    最新URLの解決を試み、成功時はキャッシュを更新して返す。
    失敗時はキャッシュがあればそれを返し（WARN ログ）、無ければ例外。

    戻り値: 使用する Excel の URL（絶対）。
    """
    base_dir = base_dir or Path.cwd()
    page_url = page_url or get_jpx_page_url()
    cache_path = cache_path or get_jpx_cache_path(base_dir)

    resolved = resolve_latest_url(page_url)
    if resolved is not None:
        write_cache(cache_path, resolved)
        return resolved

    cached = read_cache(cache_path)
    if cached is not None:
        logger.warning(
            "最新URLの取得に失敗したため、キャッシュを使用します。page_url=%s",
            page_url,
        )
        return cached

    raise RuntimeError(
        f"最新URLの取得に失敗し、キャッシュもありません。page_url={page_url} "
        "キャッシュを事前に作成するか、JPX_LIST_URL_OVERRIDE を設定してください。"
    )
