"""
Cloudflare R2（S3互換API）用 Adapter。
R2_BASE_PREFIX はバケット直下の work 用プレフィックス（例: stock-radar-system/01_work/）。
論理名 0011_work は path で渡され、key = base_prefix + path + name で結合する。
"""
from __future__ import annotations

import os
import sys
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

ENV_ACCESS_KEY_ID = "R2_ACCESS_KEY_ID"
ENV_SECRET_ACCESS_KEY = "R2_SECRET_ACCESS_KEY"
ENV_ACCOUNT_ID = "R2_ACCOUNT_ID"
ENV_BUCKET = "R2_BUCKET"
ENV_BASE_PREFIX = "R2_BASE_PREFIX"
ENV_ENDPOINT_URL = "R2_ENDPOINT_URL"


def _get_endpoint_url() -> str:
    url = os.environ.get(ENV_ENDPOINT_URL, "").strip()
    if url and "dash.cloudflare.com" in url:
        account_id = os.environ.get(ENV_ACCOUNT_ID, "").strip()
        if account_id:
            return f"https://{account_id}.r2.cloudflarestorage.com"
    if url:
        return url
    account_id = os.environ.get(ENV_ACCOUNT_ID, "").strip()
    if not account_id:
        return ""
    return f"https://{account_id}.r2.cloudflarestorage.com"


class R2StorageAdapter:
    """Cloudflare R2 用 StorageAdapter 実装。boto3 で S3 互換 API に接続する。"""

    def __init__(
        self,
        *,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        account_id: str | None = None,
        bucket: str | None = None,
        base_prefix: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._access_key_id = access_key_id or os.environ.get(ENV_ACCESS_KEY_ID, "").strip()
        self._secret_access_key = secret_access_key or os.environ.get(
            ENV_SECRET_ACCESS_KEY, ""
        ).strip()
        self._account_id = account_id or os.environ.get(ENV_ACCOUNT_ID, "").strip()
        self._bucket = bucket or os.environ.get(ENV_BUCKET, "").strip()
        self._base_prefix = base_prefix or os.environ.get(ENV_BASE_PREFIX, "").strip()
        if not self._base_prefix.endswith("/"):
            self._base_prefix += "/"
        self._endpoint_url = endpoint_url or _get_endpoint_url()
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            print(
                "エラー: R2 用に boto3 がありません。pip install boto3 を実行してください。",
                file=sys.stderr,
            )
            raise SystemExit(1) from e
        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        return self._client

    def upload_file(
        self,
        path: str,
        name: str,
        content: bytes,
        mime_type: str = "text/plain",
    ) -> str:
        key = f"{self._base_prefix}{path}{name}"
        try:
            self._get_client().put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=mime_type,
            )
            return key
        except Exception as e:
            print(f"R2 upload_file エラー: {e}", file=sys.stderr)
            raise

    def delete_older_than(self, cutoff_ym: str) -> None:
        """cutoff_ym より古い YYYY-MM のオブジェクトを削除。ページング対応。"""
        prefix = f"{self._base_prefix}{WORK_PREFIX}/"
        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        to_delete: list[dict] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                parts = key[len(prefix) :].split("/")
                if len(parts) >= 1 and parts[0]:
                    month = parts[0]
                    if len(month) == 7 and month < cutoff_ym:
                        to_delete.append({"Key": key})
        for i in range(0, len(to_delete), 1000):
            batch = to_delete[i : i + 1000]
            client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": batch, "Quiet": True},
            )


from scripts.storage.paths import WORK_PREFIX, build_day_path


if __name__ == "__main__":
    from datetime import date

    adapter = R2StorageAdapter()
    run_date = date.today()
    path = build_day_path(run_date, "work")
    content = b"test,r2,upload\n1,2,3"
    key = adapter.upload_file(path, "test_upload.txt", content, "text/plain")
    print(f"Uploaded: {key}")
