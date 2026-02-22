"""
JPX 銘柄一覧ページから最新の Excel（.xls / .xlsx）URL を抽出し、
キャッシュ更新とフォールバックを行う。
"""
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from stockradar.config import get_jpx_cache_path, get_jpx_page_url, get_jpx_page_timeout

logger = logging.getLogger(__name__)


def resolve_latest_url(page_url: str) -> str | None:
    """
    固定ページの HTML から銘柄一覧 Excel のダウンロードURLを抽出する。
    成功時は絶対URLを返し、見つからない・取得失敗時は None。
    """
    try:
        resp = requests.get(page_url, timeout=get_jpx_page_timeout())
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # 基準URL（相対パス解決用）
    base = resp.url

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith((".xls", ".xlsx")):
            continue
        absolute = urljoin(base, href)
        # 同一サイトのみ（JPX の Excel に限定）
        if urlparse(absolute).netloc == urlparse(base).netloc:
            return absolute
    return None


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
