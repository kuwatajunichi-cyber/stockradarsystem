"""
HTTP ダウンロード（例外処理付き）。
"""
import requests

from stockradar.config import get_http_timeout


def download_bytes(url: str, timeout: int | None = None) -> bytes:
    """
    指定URLからバイナリを取得する。
    HTTPエラー時は requests.HTTPError を送出する。
    """
    if timeout is None:
        timeout = get_http_timeout()
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content
