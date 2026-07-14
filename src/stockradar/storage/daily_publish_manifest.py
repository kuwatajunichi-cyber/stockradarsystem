"""Pure helpers for daily publish manifest (Phase 4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Final

from stockradar.storage.artifact_bus import resolve_logical_key

DAILY_PUBLISH_MANIFEST_KIND: Final[str] = "daily_publish"
DAILY_PUBLISH_SCHEMA_VERSION: Final[int] = 1

VISIBILITY_PREFIX: Final[dict[str, str]] = {
    "work": "0011_work",
    "paid": "0012_paid",
}

PUBLISH_BLOB_PATTERN: Final[str] = "published/{visibility}/{YYYY-MM}/{YYYY-MM-DD}/{filename}"
PUBLISH_MANIFEST_PATTERN: Final[str] = (
    "published/{visibility}/{YYYY-MM}/{YYYY-MM-DD}/manifests/{logical_kind}.json"
)


def resolve_publish_object_key(
    *,
    run_date: str,
    visibility: str,
    filename: str,
) -> str:
    prefix = VISIBILITY_PREFIX[visibility]
    return resolve_logical_key(
        PUBLISH_BLOB_PATTERN,
        run_id="0",
        run_date=run_date,
        extra={"visibility": prefix, "filename": filename},
    )


def resolve_publish_manifest_object_key(
    *,
    run_date: str,
    visibility: str,
    logical_kind: str,
) -> str:
    prefix = VISIBILITY_PREFIX[visibility]
    return resolve_logical_key(
        PUBLISH_MANIFEST_PATTERN,
        run_id="0",
        run_date=run_date,
        extra={"visibility": prefix, "logical_kind": logical_kind},
    )


def build_daily_publish_manifest(
    *,
    run_id: str,
    workflow: str,
    github_run_id: int,
    run_date: str,
    logical_kind: str,
    visibility: str,
    object_key: str,
    size_bytes: int,
    sha256: str,
    content_type: str,
    publish_id: str | None = None,
    publish_status: str = "pending",
    degraded_reason: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "manifest_kind": DAILY_PUBLISH_MANIFEST_KIND,
        "daily_publish_schema_version": DAILY_PUBLISH_SCHEMA_VERSION,
        "run_id": run_id,
        "workflow": workflow,
        "github_run_id": github_run_id,
        "run_date": run_date,
        "logical_kind": logical_kind,
        "visibility": visibility,
        "object_key": object_key,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "content_type": content_type,
        "inputs": [],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "publish_status": publish_status,
    }
    if publish_id:
        body["supabase_publish_id"] = publish_id
    if degraded_reason:
        body["degraded_reason"] = degraded_reason
    return body


def serialize_daily_publish_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
