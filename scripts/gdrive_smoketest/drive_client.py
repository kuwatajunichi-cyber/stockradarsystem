"""
Google Drive API クライアント（OAuth refresh token 方式）。
専用 Google アカウント + client_id / client_secret / refresh_token で認証する。
認証情報（Secrets）をログに出さない。
"""
from __future__ import annotations

import os
import sys
from typing import Any

# フォルダID（マイドライブ共有フォルダ）
FOLDER_ID_WORK = "1i0HfAJAwVE6o8_q-_8S8g_WVWwbLvXQs"
FOLDER_ID_PAID = "1sUA-HL04eOo9fCBa5fN1OxKRs0Sp-Wf5"
FOLDER_ID_PUBLIC = "1VftO77iFAGrx7CWPaOWPQb3xpCQO07OY"

# OAuth 環境変数名
ENV_CLIENT_ID = "GDRIVE_OAUTH_CLIENT_ID"
ENV_CLIENT_SECRET = "GDRIVE_OAUTH_CLIENT_SECRET"
ENV_REFRESH_TOKEN = "GDRIVE_OAUTH_REFRESH_TOKEN"

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def _ensure_deps() -> None:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        print(
            "エラー: Google Drive API 用の依存関係がありません。"
            " pip install google-api-python-client google-auth を実行してください。",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def get_credentials() -> Any:
    """
    環境変数 GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET / GDRIVE_OAUTH_REFRESH_TOKEN
    から OAuth Credentials を組み立てる。値はログに出さない。
    """
    _ensure_deps()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    client_id = os.environ.get(ENV_CLIENT_ID, "").strip()
    client_secret = os.environ.get(ENV_CLIENT_SECRET, "").strip()
    refresh_token = os.environ.get(ENV_REFRESH_TOKEN, "").strip()

    missing = []
    if not client_id:
        missing.append(ENV_CLIENT_ID)
    if not client_secret:
        missing.append(ENV_CLIENT_SECRET)
    if not refresh_token:
        missing.append(ENV_REFRESH_TOKEN)
    if missing:
        print(
            f"エラー: 以下の環境変数が設定されていません: {', '.join(missing)}。"
            " Repository Secrets を確認してください。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[DRIVE_SCOPE],
    )
    creds.refresh(Request())
    return creds


def build_service(credentials: Any) -> Any:
    """Drive API v3 サービスを構築する。"""
    _ensure_deps()
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def get_or_create_folder(service: Any, parent_id: str, name: str) -> str:
    """
    親フォルダ直下に name のフォルダを取得する。存在しなければ作成する。
    戻り値: フォルダの file id。
    """
    # クエリ内のシングルクォートは '' でエスケープ（Drive API）
    name_esc = name.replace("'", "''")
    q = f"'{parent_id}' in parents and name = '{name_esc}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    resp = (
        service.files()
        .list(q=q, spaces="drive", fields="files(id, name)", pageSize=2)
        .execute()
    )
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=body, fields="id").execute()
    return created["id"]


def upload_file(
    service: Any,
    parent_id: str,
    name: str,
    content: str | bytes,
    mime_type: str = "text/plain",
) -> tuple[str, str | None]:
    """
    指定親フォルダにファイルをアップロードする。
    戻り値: (file_id, web_view_link or None)
    """
    _ensure_deps()
    from io import BytesIO
    from googleapiclient.http import MediaIoBaseUpload

    if isinstance(content, str):
        content = content.encode("utf-8")
    body = {"name": name, "parents": [parent_id]}
    media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type, resumable=False)
    created = (
        service.files()
        .create(body=body, media_body=media, fields="id,webViewLink")
        .execute()
    )
    return created["id"], created.get("webViewLink")


def get_file_content(service: Any, file_id: str) -> bytes:
    """ファイル ID でファイルを取得し内容を返す。"""
    request = service.files().get_media(fileId=file_id)
    return request.execute()


def find_file_in_folder(service: Any, folder_id: str, file_name: str) -> str | None:
    """フォルダ直下で名前が file_name のファイルの ID を返す。見つからなければ None。"""
    name_esc = file_name.replace("'", "''")
    q = f"'{folder_id}' in parents and name = '{name_esc}' and trashed = false"
    resp = (
        service.files()
        .list(q=q, spaces="drive", fields="files(id)", pageSize=2)
        .execute()
    )
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def get_file_metadata(service: Any, file_id: str) -> dict:
    """ファイルのメタデータ（name, webViewLink 等）を取得する。"""
    return (
        service.files()
        .get(fileId=file_id, fields="id,name,webViewLink")
        .execute()
    )
