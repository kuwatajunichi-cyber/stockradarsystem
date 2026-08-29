"""Pure control-plane helpers for Phase 3 Supabase + R2."""
from __future__ import annotations

import re

from typing import Any, Final

PATCHED_OBJECT_KEYS_SCHEMA_VERSION: Final[int] = 1
PATCHED_UNIVERSE_CSV_FILENAME: Final[str] = "equity_domestic_core_with_name.csv"
PATCHED_UNIVERSE_MANIFEST_FILENAME: Final[str] = "manifest.json"

VALID_ROLLOUT_STAGES: Final[frozenset[str]] = frozenset({"3a", "3b", "3c"})


def normalize_rollout_stage(raw: str | None) -> str:
    stage = (raw or "3a").strip().lower()
    if stage not in VALID_ROLLOUT_STAGES:
        raise ValueError(f"invalid phase3 rollout stage: {raw!r}")
    return stage


def supabase_commit_is_fatal(stage: str) -> bool:
    return normalize_rollout_stage(stage) == "3c"


def cache_read_uses_supabase_primary(stage: str) -> bool:
    return normalize_rollout_stage(stage) in {"3b", "3c"}


def cache_read_allows_github_fallback(stage: str) -> bool:
    return normalize_rollout_stage(stage) == "3b"


def patched_select_uses_supabase_only(stage: str) -> bool:
    return normalize_rollout_stage(stage) == "3c"


def filter_patched_keys_by_allowed_refs(
    rows: list[dict[str, Any]],
    allowed_refs: frozenset[str],
) -> list[str]:
    if not allowed_refs:
        return [str(r["cache_key"]) for r in rows if r.get("cache_key")]
    return [
        str(r["cache_key"])
        for r in rows
        if r.get("cache_key") and str(r.get("source_ref") or "") in allowed_refs
    ]


def build_patched_object_keys(
    *,
    csv_object_key: str,
    csv_sha256: str,
    csv_size_bytes: int,
    manifest_object_key: str,
    manifest_sha256: str,
    manifest_size_bytes: int,
) -> dict[str, Any]:
    return {
        "cache_index_schema_version": PATCHED_OBJECT_KEYS_SCHEMA_VERSION,
        "csv": {
            "object_key": csv_object_key,
            "sha256": csv_sha256,
            "size_bytes": csv_size_bytes,
            "content_type": "text/csv",
        },
        "manifest": {
            "object_key": manifest_object_key,
            "sha256": manifest_sha256,
            "size_bytes": manifest_size_bytes,
            "content_type": "application/json",
        },
    }


def resolve_patched_r2_keys(
    *,
    monthly_tag: str,
    run_date: str,
) -> tuple[str, str]:
    base = f"cache/universe-patched/{monthly_tag}/{run_date}"
    return (
        f"{base}/equity_domestic_core_with_name.csv",
        f"{base}/manifest.json",
    )


_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def resolve_immutable_object_key(*, pattern: str, object_sha256: str) -> str:
    """Resolve create-only Layer 1 object key from mapping pattern + content sha256."""
    sha = object_sha256.strip().lower()
    if not _SHA256_RE.match(sha):
        raise ValueError(f"object_sha256 must be 64 hex chars, got {object_sha256!r}")
    templ = str(pattern or "").strip()
    if "{object_sha256}" in templ:
        return templ.replace("{object_sha256}", sha)
    if templ.endswith(".zip") and "/objects/" not in templ:
        prefix = templ.rsplit("/", 1)[0]
        return f"{prefix}/objects/sha256={sha}.zip"
    raise ValueError(
        "immutable object key pattern missing {object_sha256}: " + repr(pattern)
    )


def resolve_fixed_object_key(
    entry_id: str,
    pattern: str,
    *,
    object_sha256: str | None = None,
) -> str:
    """Prefer resolve_immutable_object_key for CAS puts."""
    if object_sha256 is not None:
        return resolve_immutable_object_key(pattern=pattern, object_sha256=object_sha256)
    mapping = {
        "cache-index-store-zip-v1": "cache/index-store-zip-v1/index_store.zip",
        "cache-ohlc-store-zip-v2": "cache/ohlc-store-zip-v2/ohlc_store.zip",
    }
    if entry_id in mapping:
        return mapping[entry_id]
    return pattern
