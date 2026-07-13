"""Load artifact/cache mapping entries from YAML (pure file read)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_MAPPING_PATH = "config/github_state_to_r2_supabase_mapping.yaml"


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def load_mapping(path: Path | None = None) -> dict[str, Any]:
    mapping_path = path or (repo_root_from_here() / DEFAULT_MAPPING_PATH)
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"mapping must be a dict: {mapping_path}")
    return data


def get_entry(entry_id: str, path: Path | None = None) -> dict[str, Any]:
    mapping = load_mapping(path)
    entries = mapping.get("entries")
    if not isinstance(entries, list):
        raise ValueError("mapping entries must be a list")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    raise KeyError(f"mapping entry not found: {entry_id}")


def phase2_daily_artifact_entry_ids() -> tuple[str, ...]:
    return (
        "artifact-daily-core-csv",
        "artifact-daily-core-quality",
        "artifact-daily-index-store",
        "artifact-daily-ohlc-store",
        "artifact-stale-exclusions",
        "artifact-daily-indicators",
        "artifact-enriched-csv",
    )


def phase3_rollout_stage(path: Path | None = None) -> str:
    from stockradar.storage.control_plane import normalize_rollout_stage

    mapping = load_mapping(path)
    return normalize_rollout_stage(str(mapping.get("phase3_rollout_stage") or "3a"))


def phase4_rollout_stage(path: Path | None = None) -> str:
    from stockradar.storage.phase4_rollout import normalize_phase4_rollout_stage

    mapping = load_mapping(path)
    return normalize_phase4_rollout_stage(str(mapping.get("phase4_rollout_stage") or "4a"))


def phase3_cache_entry_ids() -> tuple[str, ...]:
    return (
        "cache-index-store-zip-v1",
        "cache-ohlc-store-zip-v2",
        "cache-universe-patched",
    )
