"""R2 staging adapter for run artifact bus (logical key based)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Protocol

from scripts.storage.r2_client import (
    ENV_ACCESS_KEY_ID,
    ENV_ACCOUNT_ID,
    ENV_BASE_PREFIX,
    ENV_BUCKET,
    ENV_ENDPOINT_URL,
    ENV_SECRET_ACCESS_KEY,
    _get_endpoint_url,
    _load_dotenv,
)

_load_dotenv()


class R2StagingPort(Protocol):
    def put_object(
        self, logical_key: str, content: bytes, *, content_type: str = "application/octet-stream"
    ) -> str: ...

    def get_object(self, logical_key: str) -> bytes: ...

    def head_object(self, logical_key: str) -> dict[str, Any]: ...


class R2StagingAdapter:
    """Put/get/head by logical key. Applies R2_BASE_PREFIX only at I/O boundary."""

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
        while self._bucket and base.startswith(f"{self._bucket}/"):
            base = base[len(self._bucket) + 1 :]
        base = base.lstrip("/")
        if base and not base.endswith("/"):
            base += "/"
        self._base_prefix = base
        self._endpoint_url = endpoint_url or _get_endpoint_url()
        self._client = None

    def _physical_key(self, logical_key: str) -> str:
        logical = logical_key.lstrip("/")
        return f"{self._base_prefix}{logical}"

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            print(
                "エラー: R2 staging 用に boto3 がありません。pip install boto3 を実行してください。",
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

    def put_object(
        self,
        logical_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = self._physical_key(logical_key)
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return logical_key

    def get_object(self, logical_key: str) -> bytes:
        key = self._physical_key(logical_key)
        resp = self._get_client().get_object(Bucket=self._bucket, Key=key)
        body = resp["Body"].read()
        return body

    def head_object(self, logical_key: str) -> dict[str, Any]:
        key = self._physical_key(logical_key)
        resp = self._get_client().head_object(Bucket=self._bucket, Key=key)
        return {
            "logical_key": logical_key,
            "size_bytes": int(resp.get("ContentLength", 0)),
            "content_type": resp.get("ContentType", "application/octet-stream"),
        }

    def delete_objects_with_prefix(self, prefix: str) -> int:
        """Conservative cleanup path; ListObjects allowed here only."""
        client = self._get_client()
        physical_prefix = self._physical_key(prefix)
        paginator = client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=physical_prefix):
            contents = page.get("Contents") or []
            if not contents:
                continue
            batch = [{"Key": obj["Key"]} for obj in contents]
            client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
            deleted += len(batch)
        return deleted


def put_json(adapter: R2StagingPort, logical_key: str, payload: dict[str, Any]) -> str:
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return adapter.put_object(logical_key, content, content_type="application/json")


def get_json(adapter: R2StagingPort, logical_key: str) -> dict[str, Any]:
    raw = adapter.get_object(logical_key)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object at {logical_key}")
    return data
