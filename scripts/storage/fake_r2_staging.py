"""In-memory R2 staging adapter for tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeR2StagingAdapter:
    """Key-based staging store keyed by logical object key."""

    objects: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put_object(
        self,
        logical_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.objects[logical_key] = content
        self.metadata[logical_key] = {
            "size_bytes": len(content),
            "content_type": content_type,
        }
        return logical_key

    def get_object(self, logical_key: str) -> bytes:
        if logical_key not in self.objects:
            raise FileNotFoundError(f"logical key not found: {logical_key}")
        return self.objects[logical_key]

    def head_object(self, logical_key: str) -> dict[str, Any]:
        if logical_key not in self.objects:
            raise FileNotFoundError(f"logical key not found: {logical_key}")
        meta = self.metadata.get(logical_key, {})
        return {
            "logical_key": logical_key,
            "size_bytes": meta.get("size_bytes", len(self.objects[logical_key])),
            "content_type": meta.get("content_type", "application/octet-stream"),
        }

    def delete_object(self, logical_key: str) -> None:
        self.objects.pop(logical_key, None)
        self.metadata.pop(logical_key, None)

    def list_objects_with_prefix(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))
