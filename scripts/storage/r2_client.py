"""
Cloudflare R2（S3互換API）用 Adapter。
R2_BUCKET はバケット名（例: stock-radar-system）。
R2_BASE_PREFIX はバケット直下の共通プレフィックス（例: "" や "prod/"）。バケット名は含めない。
path は論理ディレクトリ（例: 0011_work/2026-03/2026-03-17/）。R2 では以下の規則で物理化する:
- 0011_work/* -> 011_work/*（work の物理プレフィックス）
- 0012_paid/* -> 0012_paid/*（paid はそのまま）
key = base_prefix + normalized_path + name で結合する。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

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
        base = (base_prefix or os.environ.get(ENV_BASE_PREFIX, "")).strip()
        # ありがちな誤設定: base_prefix にバケット名を含めてしまう（UI 表示で二重化する）。
        # 例: bucket=stock-radar-system, base_prefix=stock-radar-system/ → 実体は stock-radar-system/stock-radar-system/ になる。
        while self._bucket and base.startswith(f"{self._bucket}/"):
            base = base[len(self._bucket) + 1 :]
        base = base.lstrip("/")
        if base and not base.endswith("/"):
            base += "/"
        self._base_prefix = base
        self._endpoint_url = endpoint_url or _get_endpoint_url()
        self._client = None

    def _normalize_path(self, logical_path: str) -> str:
        # work: 0011_work -> 011_work, paid: 0012_paid はそのまま
        if logical_path.startswith("0011_work/"):
            return "011_work/" + logical_path[len("0011_work/") :]
        return logical_path

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
        key = f"{self._base_prefix}{self._normalize_path(path)}{name}"
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
        # work(011_work) と paid(0012_paid) の両方を対象にする
        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        for root in ("011_work/", "0012_paid/"):
            prefix = f"{self._base_prefix}{root}"
            to_delete: list[dict] = []
            for page in self._safe_paginate(paginator, prefix):
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

    def _safe_paginate(self, paginator, prefix: str) -> Iterator[dict]:
        """
        R2 の list_objects_v2 で NoSuchKey が返る環境差異を吸収する。
        対象プレフィックス未作成時は「空」とみなして継続する。
        """
        try:
            yield from paginator.paginate(Bucket=self._bucket, Prefix=prefix)
        except Exception as e:
            try:
                from botocore.exceptions import ClientError
            except ImportError:
                raise
            if isinstance(e, ClientError):
                code = (e.response.get("Error") or {}).get("Code")
                if code == "NoSuchKey":
                    print(
                        f"R2 list_objects_v2: prefix が存在しないためスキップします: {prefix}",
                        file=sys.stderr,
                    )
                    return
            raise


from scripts.storage.paths import build_day_path


if __name__ == "__main__":
    from datetime import date

    adapter = R2StorageAdapter()
    run_date = date.today()
    path = build_day_path(run_date, "work")
    content = b"test,r2,upload\n1,2,3"
    key = adapter.upload_file(path, "test_upload.txt", content, "text/plain")
    print(f"Uploaded: {key}")
