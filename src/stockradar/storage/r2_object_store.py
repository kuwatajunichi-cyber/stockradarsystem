"""R2 object store Protocol + Fake create-only adapter (Phase 4.5)."""
from __future__ import annotations

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


@dataclass
class FakeR2ObjectStore:
    """In-memory R2 store with create-only If-None-Match semantics."""

    objects: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

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
        key = object_key.strip()
        if key not in self.objects:
            raise FileNotFoundError(f"object not found: {key!r}")
        return self.objects[key]

    def delete_object(self, object_key: str) -> None:
        key = object_key.strip()
        self.objects.pop(key, None)
        self.metadata.pop(key, None)


def _sha256_hex(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()
