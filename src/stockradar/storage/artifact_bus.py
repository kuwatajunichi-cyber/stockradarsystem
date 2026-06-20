"""Pure run artifact bus: logical key resolution and run_artifact manifests."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from stockradar.storage.mapping_catalog import get_entry
from stockradar.utils.manifest import compute_sha256

RUN_ARTIFACT_MANIFEST_KIND = "run_artifact"
RUN_ARTIFACT_SCHEMA_VERSION = 1

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_-]+)\}")


def compact_run_date(run_date: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date):
        raise ValueError(f"run_date must be YYYY-MM-DD, got {run_date!r}")
    return run_date.replace("-", "")


def run_date_month(run_date: str) -> str:
    return run_date[:7]


def manifest_logical_key(entry_id: str, run_id: str) -> str:
    slug = entry_id.removeprefix("artifact-")
    return f"runs/daily/{run_id}/manifests/{slug}.json"


def resolve_logical_key(
    key_pattern: str,
    *,
    run_id: str,
    run_date: str,
    extra: dict[str, str] | None = None,
) -> str:
    tokens = {
        "run_id": str(run_id),
        "run_date": run_date,
        "run_date_compact": compact_run_date(run_date),
        "YYYY-MM": run_date_month(run_date),
        "YYYY-MM-DD": run_date,
    }
    if extra:
        tokens.update(extra)

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in tokens:
            raise ValueError(f"unknown placeholder {{{name}}} in pattern {key_pattern!r}")
        return tokens[name]

    resolved = _PLACEHOLDER_RE.sub(repl, key_pattern)
    if "{" in resolved or "}" in resolved:
        raise ValueError(f"unresolved placeholders remain in {resolved!r}")
    return resolved


def resolve_entry_logical_key(
    entry_id: str,
    *,
    run_id: str,
    run_date: str,
    extra: dict[str, str] | None = None,
) -> str:
    entry = get_entry(entry_id)
    pattern = entry.get("target_r2_key_pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError(f"{entry_id}: missing target_r2_key_pattern")
    return resolve_logical_key(pattern, run_id=run_id, run_date=run_date, extra=extra)


def entry_is_optional(entry_id: str) -> bool:
    entry = get_entry(entry_id)
    return bool(entry.get("optional", False))


def create_run_artifact_manifest(
    *,
    entry_id: str,
    source_name: str,
    logical_object_key: str,
    local_path: str,
    content_type: str,
    optional: bool,
    github_run_id: str,
    run_date: str,
    workflow: str = "daily.yml",
) -> dict[str, Any]:
    from pathlib import Path

    path = Path(local_path)
    size_bytes = path.stat().st_size
    sha256 = compute_sha256(path)
    return {
        "manifest_kind": RUN_ARTIFACT_MANIFEST_KIND,
        "run_artifact_schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
        "entry_id": entry_id,
        "source_name": source_name,
        "logical_object_key": logical_object_key,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "content_type": content_type,
        "optional": optional,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "github_run_id": str(github_run_id),
        "workflow": workflow,
        "run_date": run_date,
    }


def verify_run_artifact_manifest(
    manifest: dict[str, Any],
    *,
    content_sha256: str,
    size_bytes: int,
) -> tuple[bool, str]:
    if manifest.get("manifest_kind") != RUN_ARTIFACT_MANIFEST_KIND:
        return False, f"manifest_kind must be {RUN_ARTIFACT_MANIFEST_KIND!r}"
    if manifest.get("run_artifact_schema_version") != RUN_ARTIFACT_SCHEMA_VERSION:
        return False, "run_artifact_schema_version mismatch"
    expected_sha = manifest.get("sha256", "")
    if expected_sha and expected_sha != content_sha256:
        return False, "sha256 mismatch"
    expected_size = manifest.get("size_bytes")
    if expected_size is not None and int(expected_size) != size_bytes:
        return False, "size_bytes mismatch"
    return True, ""


def indicators_csv_basename(run_date: str) -> str:
    return f"indicators_{compact_run_date(run_date)}.csv"


def enriched_csv_basename(run_date: str) -> str:
    return f"indicators_event_enriched_{compact_run_date(run_date)}.csv"
