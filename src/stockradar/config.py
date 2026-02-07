"""
設定: 環境変数から読み取る。
"""
import os
from pathlib import Path

# 銘柄一覧ページ（固定。ここから最新ExcelのURLを抽出する）
DEFAULT_JPX_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"


def get_jpx_page_url() -> str:
    """最新URLを抽出する対象ページ。環境変数 JPX_PAGE_URL がなければ既定値。"""
    url = os.environ.get("JPX_PAGE_URL", "").strip()
    return url or DEFAULT_JPX_PAGE_URL


def get_jpx_list_url_override() -> str | None:
    """手動で固定する場合は JPX_LIST_URL_OVERRIDE を設定。指定時は絶対優先。"""
    url = os.environ.get("JPX_LIST_URL_OVERRIDE", "").strip()
    return url or None


def get_jpx_cache_path(base_dir: Path) -> Path:
    """キャッシュURLを保存するファイルパス。"""
    return base_dir / "data" / "cache" / "jpx_latest_url.txt"
