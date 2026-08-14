"""R2 object store Protocol + Fake create-only adapter (Phase 4.5)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class R2ObjectAlreadyExistsError(RuntimeError):
    """Object key already exists with different bytes — exit 2 contract."""


@dataclass(frozen=True)
class R2HeadResult:
    object_key: str
    size_bytes: int
    byte_sha256: str
    content_type: str


@dataclass(frozen=True)
class R2PutResult:
    object_key: str
    size_bytes: int
    byte_sha256: str
    content_type: str
    noop: bool = False


class R2ObjectStorePort(Protocol):
    def put_create_only(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> R2PutResult: ...

    def head_object(self, object_key: str) -> R2HeadResult: ...

    def get_object(self, object_key: str) -> bytes: ...


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass
class FakeR2ObjectStore:
    """In-memory R2 store with create-only If-None-Match semantics."""

    objects: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._lock is None:
            from threading import RLock

            object.__setattr__(self, "_lock", RLock())

    def put_create_only(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> R2PutResult:
        with self._lock:
            return self._put_create_only_unlocked(
                object_key, content, content_type=content_type
            )

    def _put_create_only_unlocked(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> R2PutResult:
        key = object_key.strip()
        digest = _sha256_hex(content)
        size_bytes = len(content)
        if key in self.objects:
            existing = self.objects[key]
            if existing == content:
                meta = self.metadata.get(key, {})
                return R2PutResult(
                    object_key=key,
                    size_bytes=size_bytes,
                    byte_sha256=digest,
                    content_type=str(meta.get("content_type") or content_type),
                    noop=True,
                )
            raise R2ObjectAlreadyExistsError(
                f"object already exists with different bytes: {key!r}"
            )
        self.objects[key] = content
        self.metadata[key] = {
            "size_bytes": size_bytes,
            "byte_sha256": digest,
            "content_type": content_type,
        }
        return R2PutResult(
            object_key=key,
            size_bytes=size_bytes,
            byte_sha256=digest,
            content_type=content_type,
            noop=False,
        )

    def head_object(self, object_key: str) -> R2HeadResult:
        with self._lock:
            return self._head_object_unlocked(object_key)

    def _head_object_unlocked(self, object_key: str) -> R2HeadResult:
        key = object_key.strip()
        if key not in self.objects:
            raise FileNotFoundError(f"object not found: {key!r}")
        content = self.objects[key]
        meta = self.metadata.get(key, {})
        return R2HeadResult(
            object_key=key,
            size_bytes=int(meta.get("size_bytes", len(content))),
            byte_sha256=str(meta.get("byte_sha256") or _sha256_hex(content)),
            content_type=str(meta.get("content_type") or "application/octet-stream"),
        )

    def get_object(self, object_key: str) -> bytes:
        with self._lock:
            return self._get_object_unlocked(object_key)

    def _get_object_unlocked(self, object_key: str) -> bytes:
        key = object_key.strip()
        if key not in self.objects:
            raise FileNotFoundError(f"object not found: {key!r}")
        return self.objects[key]

    def delete_object(self, object_key: str) -> None:
        with self._lock:
            return self._delete_object_unlocked(object_key)

    def _delete_object_unlocked(self, object_key: str) -> None:
        key = object_key.strip()
        self.objects.pop(key, None)
        self.metadata.pop(key, None)


ENV_R2_ACCESS_KEY_ID = "R2_ACCESS_KEY_ID"
ENV_R2_SECRET_ACCESS_KEY = "R2_SECRET_ACCESS_KEY"
ENV_R2_ACCOUNT_ID = "R2_ACCOUNT_ID"
ENV_R2_BUCKET = "R2_BUCKET"
ENV_R2_BASE_PREFIX = "R2_BASE_PREFIX"
ENV_R2_ENDPOINT_URL = "R2_ENDPOINT_URL"


def _r2_endpoint_url() -> str:
    url = os.environ.get(ENV_R2_ENDPOINT_URL, "").strip()
    if url and "dash.cloudflare.com" in url:
        account_id = os.environ.get(ENV_R2_ACCOUNT_ID, "").strip()
        if account_id:
            return f"https://{account_id}.r2.cloudflarestorage.com"
    if url:
        return url
    account_id = os.environ.get(ENV_R2_ACCOUNT_ID, "").strip()
    if not account_id:
        return ""
    return f"https://{account_id}.r2.cloudflarestorage.com"


@dataclass
class S3R2ObjectStore:
    """Cloudflare R2 create-only object store (If-None-Match semantics)."""

    access_key_id: str
    secret_access_key: str
    bucket: str
    base_prefix: str
    endpoint_url: str
    max_pool_connections: int = 32
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> S3R2ObjectStore:
        access_key_id = os.environ.get(ENV_R2_ACCESS_KEY_ID, "").strip()
        secret_access_key = os.environ.get(ENV_R2_SECRET_ACCESS_KEY, "").strip()
        bucket = os.environ.get(ENV_R2_BUCKET, "").strip()
        base = os.environ.get(ENV_R2_BASE_PREFIX, "").strip()
        while bucket and base.startswith(f"{bucket}/"):
            base = base[len(bucket) + 1 :]
        base = base.lstrip("/")
        if base and not base.endswith("/"):
            base += "/"
        endpoint_url = _r2_endpoint_url()
        missing = [
            name
            for name, value in (
                (ENV_R2_ACCESS_KEY_ID, access_key_id),
                (ENV_R2_SECRET_ACCESS_KEY, secret_access_key),
                (ENV_R2_BUCKET, bucket),
                ("R2 endpoint", endpoint_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"R2 configuration required: {', '.join(missing)}")
        pool = int(os.environ.get("DERIVED_R2_CONCURRENCY", "32") or "32")
        if pool < 1:
            pool = 1
        return cls(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            bucket=bucket,
            base_prefix=base,
            endpoint_url=endpoint_url,
            max_pool_connections=max(pool, 10),
        )

    def _physical_key(self, logical_key: str) -> str:
        logical = logical_key.lstrip("/")
        return f"{self.base_prefix}{logical}"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3R2ObjectStore") from exc
        pool = max(int(self.max_pool_connections), 1)
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                max_pool_connections=pool,
            ),
        )
        return self._client

    def warm_client(self) -> None:
        """Eager-init boto3 client before ThreadPool workers race lazy init."""
        self._get_client()

    def put_create_only(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> R2PutResult:
        key = object_key.strip()
        digest = _sha256_hex(content)
        size_bytes = len(content)
        physical = self._physical_key(key)
        client = self._get_client()
        try:
            from botocore.exceptions import ClientError

            client.put_object(
                Bucket=self.bucket,
                Key=physical,
                Body=content,
                ContentType=content_type,
                IfNoneMatch="*",
            )
            return R2PutResult(
                object_key=key,
                size_bytes=size_bytes,
                byte_sha256=digest,
                content_type=content_type,
                noop=False,
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"PreconditionFailed", "412"}:
                raise
            existing = self.get_object(key)
            if existing == content:
                head = self.head_object(key)
                return R2PutResult(
                    object_key=key,
                    size_bytes=head.size_bytes,
                    byte_sha256=head.byte_sha256,
                    content_type=head.content_type,
                    noop=True,
                )
            raise R2ObjectAlreadyExistsError(
                f"object already exists with different bytes: {key!r}"
            ) from exc

    def head_object(self, object_key: str) -> R2HeadResult:
        key = object_key.strip()
        physical = self._physical_key(key)
        resp = self._get_client().head_object(Bucket=self.bucket, Key=physical)
        content = self.get_object(key)
        return R2HeadResult(
            object_key=key,
            size_bytes=int(resp.get("ContentLength", len(content))),
            byte_sha256=_sha256_hex(content),
            content_type=str(resp.get("ContentType") or "application/octet-stream"),
        )

    def get_object(self, object_key: str) -> bytes:
        key = object_key.strip()
        physical = self._physical_key(key)
        resp = self._get_client().get_object(Bucket=self.bucket, Key=physical)
        return resp["Body"].read()
