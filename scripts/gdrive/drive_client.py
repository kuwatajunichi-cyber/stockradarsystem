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
import time
import uuid
import importlib.util
from collections.abc import Callable
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
    has_creds = importlib.util.find_spec("google.oauth2.credentials") is not None
    has_discovery = importlib.util.find_spec("googleapiclient.discovery") is not None
    if not (has_creds and has_discovery):
        print(
            "エラー: Google Drive API 用の依存関係がありません。"
            " pip install google-api-python-client google-auth を実行してください。",
            file=sys.stderr,
        )
        raise SystemExit(1)


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


# Google の 502 ページは「30 秒後に再試行」と案内する。初回は短く、最後はそれに合わせる。
_DRIVE_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (5.0, 15.0, 30.0)
_DRIVE_RETRY_MAX_ATTEMPTS = 4
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


def _http_status(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_retryable_drive_error(exc: BaseException) -> bool:
    """502 などの一時障害と接続断だけを再試行する。認証エラーは再試行しない。"""
    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
        return False
    if _http_status(exc) in _RETRYABLE_HTTP_STATUS:
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    module = type(exc).__module__
    name = type(exc).__name__
    return name in {"TransportError", "Timeout", "IncompleteRead"} and (
        module.startswith("google.")
        or module.startswith("httplib2")
        or module.startswith("urllib")
        or module.startswith("http.")
    )


def _call_with_retry(operation: Callable[[], Any], *, what: str) -> Any:
    """一時的な Drive API 失敗をバックオフして再実行する。"""
    last: BaseException | None = None
    attempts = _DRIVE_RETRY_MAX_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_drive_error(exc) or attempt >= attempts:
                raise
            delay = _DRIVE_RETRY_BACKOFF_SECONDS[
                min(attempt - 1, len(_DRIVE_RETRY_BACKOFF_SECONDS) - 1)
            ]
            status = _http_status(exc)
            status_text = f"HTTP {status}" if status is not None else type(exc).__name__
            print(
                f"[Drive] {what} 一時エラー {status_text}。"
                f"{delay:.0f}s 後に再試行 ({attempt}/{attempts})",
                file=sys.stderr,
            )
            time.sleep(delay)
            last = exc
    assert last is not None
    raise last


def _escape_drive_query(value: str) -> str:
    return value.replace("'", "''")


def _list_named_children(
    service: Any,
    parent_id: str,
    name: str,
    *,
    folder: bool,
) -> list[dict[str, Any]]:
    """親直下の同名アイテムを、更新日時の新しい順で返す。"""
    name_esc = _escape_drive_query(name)
    mime_clause = (
        "mimeType = 'application/vnd.google-apps.folder'"
        if folder
        else "mimeType != 'application/vnd.google-apps.folder'"
    )
    query = (
        f"'{parent_id}' in parents and name = '{name_esc}' "
        f"and {mime_clause} and trashed = false"
    )
    found: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "q": query,
            "spaces": "drive",
            "fields": "nextPageToken, files(id, name, modifiedTime)",
            "pageSize": 100,
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.files().list(**kwargs).execute()
        found.extend(resp.get("files") or [])
        page_token = resp.get("nextPageToken") or None
        if not page_token:
            break
    found.sort(key=lambda item: str(item.get("modifiedTime") or ""), reverse=True)
    return found


def _newest_child_id(service: Any, parent_id: str, name: str, *, folder: bool) -> str | None:
    """同名のうち更新日時が最新の ID。フォルダが複数あっても削除しない。"""
    files = _list_named_children(service, parent_id, name, folder=folder)
    if not files:
        return None
    if folder and len(files) > 1:
        print(
            f"[Drive] 同名フォルダが{len(files)}件あります。最新を使います。"
            f"フォルダは削除しません: {name}",
            file=sys.stderr,
        )
    return str(files[0]["id"])


def get_or_create_folder(service: Any, parent_id: str, name: str) -> str:
    """
    親フォルダ直下に name のフォルダを取得する。存在しなければ作成する。
    一時的な 5xx / 429 は再試行し、作成成功後に応答だけ失った場合は再検索する。
    戻り値: フォルダの file id。
    """

    def _once() -> str:
        existing = _newest_child_id(service, parent_id, name, folder=True)
        if existing:
            return existing
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        created = service.files().create(body=body, fields="id").execute()
        return str(created["id"])

    return str(_call_with_retry(_once, what=f"folder {name}"))


def upload_file(
    service: Any,
    parent_id: str,
    name: str,
    content: str | bytes,
    mime_type: str = "text/plain",
) -> tuple[str, str | None]:
    """
    指定親フォルダにファイルをアップロードする。
    同名ファイルがあれば更新日時が最新の1件を上書きし、残りの同名はゴミ箱へ移す。
    同名が無ければ作成する。ゴミ箱への移動に失敗しても、上書き済みの file_id は返す。
    一時的な 5xx / 429 は再試行する。再試行前に同名を探し直す。
    戻り値: (file_id, web_view_link or None)
    """
    _ensure_deps()
    from io import BytesIO
    from googleapiclient.http import MediaIoBaseUpload

    if isinstance(content, str):
        payload = content.encode("utf-8")
    else:
        payload = content

    def _once() -> tuple[str, str | None, list[str]]:
        matches = _list_named_children(service, parent_id, name, folder=False)
        media = MediaIoBaseUpload(BytesIO(payload), mimetype=mime_type, resumable=False)
        files_api = service.files()
        if matches:
            keeper = str(matches[0]["id"])
            created = files_api.update(
                fileId=keeper,
                media_body=media,
                fields="id,webViewLink",
            ).execute()
            file_id = str(created["id"])
            stale = [str(item["id"]) for item in matches[1:] if str(item["id"]) != file_id]
            if stale:
                print(
                    f"[Drive] 同名が{len(matches)}件あります。最新を上書きし、"
                    f"残りをゴミ箱へ移動します: {name}",
                    file=sys.stderr,
                )
            return file_id, created.get("webViewLink"), stale
        body = {"name": name, "parents": [parent_id]}
        created = files_api.create(
            body=body,
            media_body=media,
            fields="id,webViewLink",
        ).execute()
        return str(created["id"]), created.get("webViewLink"), []

    file_id, link, stale_ids = _call_with_retry(_once, what=f"upload {name}")
    for stale_id in stale_ids:
        _trash_named_duplicate(service, stale_id, name)
    return file_id, link


def _trash_named_duplicate(service: Any, file_id: str, name: str) -> None:
    """古い同名をゴミ箱へ移す。失敗してもアップロード結果は変えない。"""

    def _once() -> None:
        service.files().update(
            fileId=file_id,
            body={"trashed": True},
            fields="id",
        ).execute()

    try:
        _call_with_retry(_once, what=f"trash {name}")
    except Exception as exc:
        print(
            f"[Drive] 同名の古いファイルをゴミ箱へ移動できませんでした: {name} ({file_id}): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return
    print(
        f"[Drive] 同名の古いファイルをゴミ箱へ移動しました: {name} ({file_id})",
        file=sys.stderr,
    )


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
        """指定親フォルダにファイルをアップロードする。同名は最新1件を上書きし、残りは捨てる。戻り値: (file_id, web_view_link or None)。"""
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
    upload_file は同じ親・同じ名前があれば最後に置いた1件を上書きし、それ以外の同名は捨てる。
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
        matches = [
            fid
            for fid, meta in self._files.items()
            if meta.get("parent_id") == parent_id and meta.get("name") == name
        ]
        if matches:
            keeper = matches[-1]
            for fid in matches:
                if fid != keeper:
                    del self._files[fid]
            self._files[keeper] = {
                "content": content,
                "name": name,
                "parent_id": parent_id,
            }
            return keeper, None
        file_id = str(uuid.uuid4())
        self._files[file_id] = {
            "content": content,
            "name": name,
            "parent_id": parent_id,
        }
        return file_id, None

    def get_or_create_folder(self, parent_id: str, name: str) -> str:
        """Fake ではフォルダは扱わず、parent_id をそのまま返す（同一 ID でアップロード先とする）。"""
        return parent_id
