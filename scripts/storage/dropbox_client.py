"""
Dropbox 用 Adapter。
DROPBOX_BASE_FOLDER は App Folder 直下の work 用フォルダ（例: /Apps/stock-radar-system/011_work）。
論理名 0011_work は path で渡され、full_path = DROPBOX_BASE_FOLDER + '/' + path + name。
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path

# プロジェクトルートの .env を読み込む
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local")


_load_dotenv()

ENV_APP_KEY = "DROPBOX_APP_KEY"
ENV_APP_SECRET = "DROPBOX_APP_SECRET"
ENV_REFRESH_TOKEN = "DROPBOX_REFRESH_TOKEN"
ENV_BASE_FOLDER = "DROPBOX_BASE_FOLDER"

TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
DELETE_URL = "https://api.dropboxapi.com/2/files/delete_v2"
UPLOAD_RETRY_MAX = 8
UPLOAD_BACKOFF_BASE_SEC = 1
UPLOAD_BACKOFF_CAP_SEC = 30

# 月フォルダ名 YYYY-MM のパターン
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_access_token(
    app_key: str,
    app_secret: str,
    refresh_token: str,
) -> str:
    import base64

    import requests

    auth = base64.b64encode(f"{app_key}:{app_secret}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Authorization": f"Basic {auth}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


class DropboxStorageAdapter:
    """Dropbox 用 StorageAdapter 実装。REST API で App Folder にアップロード・削除する。"""

    def __init__(
        self,
        *,
        app_key: str | None = None,
        app_secret: str | None = None,
        refresh_token: str | None = None,
        base_folder: str | None = None,
    ) -> None:
        self._app_key = app_key or os.environ.get(ENV_APP_KEY, "").strip()
        self._app_secret = app_secret or os.environ.get(ENV_APP_SECRET, "").strip()
        self._refresh_token = refresh_token or os.environ.get(ENV_REFRESH_TOKEN, "").strip()
        self._base_folder = base_folder or os.environ.get(ENV_BASE_FOLDER, "").strip()
        # App folder 権限の Dropbox API は、パス指定が「アプリフォルダ内ルート」基準になる。
        # UI の `Apps/stock-radar-system` は暗黙のルートなので、base_folder に含めると二重化して見える。
        if self._base_folder.startswith("http"):
            self._base_folder = ""
        self._base_folder = self._base_folder.strip()
        if self._base_folder in ("/", ""):
            self._base_folder = ""
        # 誤って /Apps/stock-radar-system を渡した場合は、アプリルートに正規化する
        if self._base_folder.startswith("/Apps/stock-radar-system"):
            self._base_folder = ""
        # それ以外で相対パスが来た場合は / を付ける（ルート下のサブフォルダとして扱う）
        if self._base_folder and not self._base_folder.startswith("/"):
            self._base_folder = "/" + self._base_folder.rstrip("/")
        self._access_token: str | None = None
        self._upload_retry_max = _env_int("DROPBOX_UPLOAD_RETRY_MAX", UPLOAD_RETRY_MAX)
        self._upload_backoff_base_sec = _env_int("DROPBOX_UPLOAD_BACKOFF_BASE_SEC", UPLOAD_BACKOFF_BASE_SEC)
        self._upload_backoff_cap_sec = _env_int("DROPBOX_UPLOAD_BACKOFF_CAP_SEC", UPLOAD_BACKOFF_CAP_SEC)

    def _normalize_path(self, logical_path: str) -> str:
        # work: 0011_work -> 011_work, paid: 0012_paid はそのまま
        if logical_path.startswith("0011_work/"):
            return "011_work/" + logical_path[len("0011_work/") :]
        return logical_path

    def _get_access_token(self) -> str:
        if self._access_token is None:
            self._access_token = _get_access_token(
                self._app_key,
                self._app_secret,
                self._refresh_token,
            )
        return self._access_token

    def upload_file(
        self,
        path: str,
        name: str,
        content: bytes,
        mime_type: str = "text/plain",
    ) -> str:
        import requests

        # path は末尾 / を含む論理パス（例: 0011_work/... or 0012_paid/...）を想定。
        # Dropbox では work を 011_work に正規化して格納する。
        norm = self._normalize_path(path)
        if self._base_folder:
            full_path = f"{self._base_folder.rstrip('/')}/{norm.strip('/')}/{name}"
        else:
            full_path = f"/{norm.strip('/')}/{name}"
        full_path = full_path.replace("//", "/")
        arg = json.dumps({"path": full_path, "mode": "overwrite"})
        token = self._get_access_token()
        retry_max = max(0, self._upload_retry_max)
        backoff_base = max(1, self._upload_backoff_base_sec)
        backoff_cap = max(backoff_base, self._upload_backoff_cap_sec)
        for attempt in range(retry_max + 1):
            resp = requests.post(
                UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Dropbox-API-Arg": arg,
                    "Content-Type": "application/octet-stream",
                },
                data=content,
                timeout=60,
            )
            if resp.status_code == 200:
                return full_path

            # Dropbox の書き込みレート制限は短時間で解消することが多いため、retry_after を優先して再試行する。
            should_retry = resp.status_code in (429, 500, 502, 503, 504)
            if should_retry and attempt < retry_max:
                retry_after = 1
                try:
                    body = resp.json()
                    retry_after = int(body.get("error", {}).get("retry_after", retry_after))
                except Exception:
                    pass
                retry_after = max(1, retry_after)
                exp_backoff = min(backoff_cap, backoff_base * (2**attempt))
                # サーバー指示(retry_after)を下限にしつつ、軽いジッターを加えて衝突を避ける。
                wait_sec = max(retry_after, exp_backoff) + random.uniform(0.0, 0.5)
                print(
                    f"Dropbox upload_file リトライ: status={resp.status_code} wait={wait_sec:.2f}s attempt={attempt + 1}/{retry_max}",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue

            print(f"Dropbox upload_file エラー: {resp.status_code} {resp.text}", file=sys.stderr)
            resp.raise_for_status()

        raise RuntimeError("Dropbox upload_file: unexpected fallthrough")

    def delete_older_than(self, cutoff_ym: str) -> None:
        """cutoff_ym より古い YYYY-MM フォルダを削除。work(011_work) / paid(0012_paid) 両方対象。"""
        import requests

        token = self._get_access_token()
        for root in ("011_work", "0012_paid"):
            list_path = f"{self._base_folder.rstrip('/')}/{root}" if self._base_folder else f"/{root}"
            resp = requests.post(
                LIST_FOLDER_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"path": list_path, "recursive": False},
                timeout=30,
            )
            if resp.status_code != 200:
                if resp.status_code == 409:
                    body = resp.json()
                    if body.get("error", {}).get(".tag") == "path":
                        continue
                print(f"Dropbox list_folder エラー: {resp.status_code} {resp.text}", file=sys.stderr)
                resp.raise_for_status()
            data = resp.json()
            for entry in data.get("entries") or []:
                if entry.get(".tag") != "folder":
                    continue
                name = entry.get("name", "")
                if not MONTH_PATTERN.match(name):
                    continue
                if name < cutoff_ym:
                    folder_path = entry.get("path_display") or entry.get("path_lower") or f"{list_path}/{name}"
                    del_resp = requests.post(
                        DELETE_URL,
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json={"path": folder_path},
                        timeout=30,
                    )
                    if del_resp.status_code not in (200, 409):
                        print(f"Dropbox delete エラー: {del_resp.status_code} {del_resp.text}", file=sys.stderr)
                        del_resp.raise_for_status()


if __name__ == "__main__":
    from datetime import date

    from scripts.storage.paths import build_day_path

    adapter = DropboxStorageAdapter()
    run_date = date.today()
    path = build_day_path(run_date, "work")
    content = b"test,dropbox,upload\n1,2,3"
    full_path = adapter.upload_file(path, "test_upload.txt", content, "text/plain")
    print(f"Uploaded: {full_path}")
