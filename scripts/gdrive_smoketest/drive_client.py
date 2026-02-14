"""
Google Drive API クライアント（Service Account 利用）。
GDRIVE_SA_JSON の内容をログに出さない。
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# フォルダID（マイドライブ共有フォルダ）
FOLDER_ID_WORK = "1i0HfAJAwVE6o8_q-_8S8g_WVWwbLvXQs"
FOLDER_ID_PAID = "1sUA-HL04eOo9fCBa5fN1OxKRs0Sp-Wf5"
FOLDER_ID_PUBLIC = "1VftO77iFAGrx7CWPaOWPQb3xpCQO07OY"


def _ensure_deps() -> None:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError as e:
        print(
            "エラー: Google Drive API 用の依存関係がありません。"
            " pip install google-api-python-client google-auth を実行してください。",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def get_credentials(env_var: str = "GDRIVE_SA_JSON") -> Any:
    """環境変数から Service Account JSON を読み、Credentials を返す。"""
    _ensure_deps()
    from google.oauth2 import service_account

    raw = os.environ.get(env_var)
    if not raw:
        print(
            f"エラー: 環境変数 {env_var} が設定されていません。"
            " Repository Secret を確認してください。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        print(
            f"エラー: {env_var} の内容が有効な JSON ではありません。",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    return service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )


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
    q = f"'{parent_id}' in parents and name = '{name.replace(chr(39), chr(39)+chr(39))}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
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
    q = f"'{folder_id}' in parents and name = '{file_name.replace(chr(39), chr(39)+chr(39))}' and trashed = false"
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
