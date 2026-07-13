"""Pure helpers for Phase 4 monthly snapshot aggregate manifest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

MONTHLY_SNAPSHOT_MANIFEST_KIND: Final[str] = "monthly_snapshot"
MONTHLY_SNAPSHOT_SCHEMA_VERSION: Final[int] = 1

MONTHLY_CSV_NAMES: Final[tuple[str, ...]] = (
    "equity_domestic_ipo_with_name.csv",
    "equity_domestic_illiquid_with_name.csv",
    "equity_domestic_core_with_name.csv",
)


def _blob_spec(
    *,
    object_key: str,
    sha256: str,
    size_bytes: int,
    content_type: str,
) -> dict[str, Any]:
    return {
        "object_key": object_key,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "content_type": content_type,
    }


def build_monthly_object_keys(
    *,
    monthly_tag: str,
    ipo_sha256: str,
    ipo_size: int,
    illiquid_sha256: str,
    illiquid_size: int,
    core_sha256: str,
    core_size: int,
    manifest_sha256: str,
    manifest_size: int,
) -> dict[str, Any]:
    base = f"monthly/{monthly_tag}"
    return {
        "monthly_snapshots_schema_version": MONTHLY_SNAPSHOT_SCHEMA_VERSION,
        "ipo": _blob_spec(
            object_key=f"{base}/equity_domestic_ipo_with_name.csv",
            sha256=ipo_sha256,
            size_bytes=ipo_size,
            content_type="text/csv",
        ),
        "illiquid": _blob_spec(
            object_key=f"{base}/equity_domestic_illiquid_with_name.csv",
            sha256=illiquid_sha256,
            size_bytes=illiquid_size,
            content_type="text/csv",
        ),
        "core": _blob_spec(
            object_key=f"{base}/equity_domestic_core_with_name.csv",
            sha256=core_sha256,
            size_bytes=core_size,
            content_type="text/csv",
        ),
        "manifest": _blob_spec(
            object_key=f"{base}/manifest.json",
            sha256=manifest_sha256,
            size_bytes=manifest_size,
            content_type="application/json",
        ),
    }


def build_monthly_snapshot_manifest(
    *,
    staging_dir: Path,
    monthly_tag: str,
    github_run_id: int,
    snapshot_date: str,
) -> dict[str, Any]:
    outputs: list[dict[str, Any]] = []
    for csv_name in MONTHLY_CSV_NAMES:
        csv_path = staging_dir / csv_name
        manifest_path = staging_dir / f"{csv_name}.manifest.json"
        if not csv_path.is_file():
            raise FileNotFoundError(f"missing csv: {csv_path}")
        if not manifest_path.is_file():
            raise FileNotFoundError(f"missing per-csv manifest: {manifest_path}")
        per_csv = json.loads(manifest_path.read_text(encoding="utf-8"))
        outputs.append(
            {
                "logical_name": csv_name,
                "sha256": per_csv.get("output", {}).get("sha256") or per_csv.get("sha256"),
                "size_bytes": per_csv.get("output", {}).get("size_bytes") or per_csv.get("size_bytes"),
            }
        )

    body: dict[str, Any] = {
        "manifest_kind": MONTHLY_SNAPSHOT_MANIFEST_KIND,
        "monthly_snapshot_schema_version": MONTHLY_SNAPSHOT_SCHEMA_VERSION,
        "monthly_tag": monthly_tag,
        "github_run_id": github_run_id,
        "snapshot_date": snapshot_date,
        "outputs": outputs,
    }
    return body


def serialize_monthly_snapshot_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
