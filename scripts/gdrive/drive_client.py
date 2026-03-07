"""
Google Drive API クライアント（OAuth refresh token 方式）。
専用 Google アカウント + client_id / client_secret / refresh_token で認証する。
認証情報（Secrets）をログに出さない。

ローカルではプロジェクトルートの .env を自動読み込みする（python-dotenv）。
CI では環境変数または GitHub Secrets をそのまま使用。

DriveAdapter Protocol により、本番は GoogleDriveAdapter、テストは FakeDriveAdapter を注入可能。
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

# プロジェクトルートの .env を読み込む（import 時に1回だけ）
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local")  # .env.local があれば優先して上書き


_load_dotenv()

# フォルダID（マイドライブ共有フォルダ）のデフォルト値
_DEFAULT_FOLDER_ID_WORK = "1i0HfAJAwVE6o8_q-_8S8g_WVWwbLvXQs"
_DEFAULT_FOLDER_ID_PAID = "1sUA-HL04eOo9fCBa5fN1OxKRs0Sp-Wf5"
_DEFAULT_FOLDER_ID_PUBLIC = "1VftO77iFAGrx7CWPaOWPQb3xpCQO07OY"


def get_folder_id_work() -> str:
    """作業用フォルダID。環境変数 GDRIVE_FOLDER_ID_WORK で上書き可能。"""
    return os.environ.get("GDRIVE_FOLDER_ID_WORK", "").strip() or _DEFAULT_FOLDER_ID_WORK


def get_folder_id_paid() -> str:
    """有料成果物フォルダID。環境変数 GDRIVE_FOLDER_ID_PAID で上書き可能。"""
    return os.environ.get("GDRIVE_FOLDER_ID_PAID", "").strip() or _DEFAULT_FOLDER_ID_PAID


def get_folder_id_public() -> str:
    """公開フォルダID。環境変数 GDRIVE_FOLDER_ID_PUBLIC で上書き可能。"""
    return os.environ.get("GDRIVE_FOLDER_ID_PUBLIC", "").strip() or _DEFAULT_FOLDER_ID_PUBLIC


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


def get_credentials(extra_scopes: list[str] | None = None) -> Any:
    """
    環境変数 GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET / GDRIVE_OAUTH_REFRESH_TOKEN
    から OAuth Credentials を組み立てる。値はログに出さない。

    extra_scopes: 追加スコープ（オプション）
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

    scopes = [DRIVE_SCOPE]
    if extra_scopes:
        scopes = list(scopes) + list(extra_scopes)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
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


def get_file_metadata(service: Any, file_id: str) -> dict:
    """ファイルのメタデータ（name, webViewLink 等）を取得する。"""
    return (
        service.files()
        .get(fileId=file_id, fields="id,name,webViewLink")
        .execute()
    )


# --- DriveAdapter Protocol と実装 ---


class DriveAdapter(Protocol):
    """Drive のファイル取得・アップロード・フォルダ操作の抽象。テスト時に Fake を注入可能。"""

    def get_file_content(self, file_id: str) -> bytes:
        """ファイル ID で内容を取得する。"""
        ...

    def get_file_metadata(self, file_id: str) -> dict:
        """ファイルのメタデータ（name, webViewLink 等）を取得する。"""
        ...

    def upload_file(
        self,
        parent_id: str,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain",
    ) -> tuple[str, str | None]:
        """指定親フォルダにファイルをアップロードする。戻り値: (file_id, web_view_link or None)。"""
        ...

    def get_or_create_folder(self, parent_id: str, name: str) -> str:
        """親フォルダ直下に name のフォルダを取得または作成する。戻り値: フォルダの file id。"""
        ...


class GoogleDriveAdapter:
    """既存の Drive API service をラップする DriveAdapter 実装。"""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_file_content(self, file_id: str) -> bytes:
        return get_file_content(self._service, file_id)

    def get_file_metadata(self, file_id: str) -> dict:
        return get_file_metadata(self._service, file_id)

    def upload_file(
        self,
        parent_id: str,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain",
    ) -> tuple[str, str | None]:
        return upload_file(self._service, parent_id, name, content, mime_type)

    def get_or_create_folder(self, parent_id: str, name: str) -> str:
        return get_or_create_folder(self._service, parent_id, name)


class FakeDriveAdapter:
    """
    テスト用: メモリ上にファイルを保持する DriveAdapter 実装。
    get_file_content は事前に登録した file_id -> bytes を返す。
    upload_file は偽の file_id を発行して内容を保存する（get_file_content で取得可能）。
    """

    def __init__(self) -> None:
        # file_id -> {"content": bytes, "name": str}
        self._files: dict[str, dict[str, Any]] = {}

    def put_file(self, file_id: str, content: bytes, name: str = "") -> None:
        """テスト用: 指定 file_id で内容を登録する。"""
        self._files[file_id] = {"content": content, "name": name or file_id}

    def get_file_content(self, file_id: str) -> bytes:
        if file_id not in self._files:
            raise KeyError(f"File not found: {file_id}")
        return self._files[file_id]["content"]

    def get_file_metadata(self, file_id: str) -> dict:
        if file_id not in self._files:
            raise KeyError(f"File not found: {file_id}")
        name = self._files[file_id].get("name", file_id)
        return {"id": file_id, "name": name, "webViewLink": None}

    def upload_file(
        self,
        parent_id: str,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain",
    ) -> tuple[str, str | None]:
        if isinstance(content, str):
            content = content.encode("utf-8")
        file_id = str(uuid.uuid4())
        self._files[file_id] = {"content": content, "name": name}
        return file_id, None

    def get_or_create_folder(self, parent_id: str, name: str) -> str:
        """Fake ではフォルダは扱わず、parent_id をそのまま返す（同一 ID でアップロード先とする）。"""
        return parent_id
