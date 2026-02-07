"""
設定: 環境変数から読み取る。
"""
import os


def get_jpx_list_url() -> str:
    """JPX銘柄一覧のダウンロードURL。環境変数 JPX_LIST_URL から取得。"""
    url = os.environ.get("JPX_LIST_URL")
    if not url or not url.strip():
        raise ValueError(
            "環境変数 JPX_LIST_URL が未設定です。"
            "例: $env:JPX_LIST_URL='https://...' (PowerShell)"
        )
    return url.strip()
