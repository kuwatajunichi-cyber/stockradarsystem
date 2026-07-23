"""Phase 4.5 rollout stage helpers (Issue #93)."""
from __future__ import annotations

import os
from typing import Any, Final, Mapping

VALID_PHASE4_5_STAGES: Final[frozenset[str]] = frozenset({"off", "4.5a", "4.5b", "4.5c"})

RunMode = str  # normal | replay | backfill | reconcile


def normalize_phase4_5_rollout_stage(raw: str | None) -> str:
    stage = (raw or "off").strip().lower()
    if stage not in VALID_PHASE4_5_STAGES:
        raise ValueError(f"invalid phase4_5 rollout stage: {raw!r}")
    return stage


def derived_writer_enabled(stage: str) -> bool:
    return normalize_phase4_5_rollout_stage(stage) != "off"


def derived_shadow_snapshot_write_enabled(stage: str) -> bool:
    return normalize_phase4_5_rollout_stage(stage) in {"4.5a", "4.5b", "4.5c"}


def derived_shadow_series_write_enabled(stage: str) -> bool:
    return normalize_phase4_5_rollout_stage(stage) in {"4.5b", "4.5c"}


def derived_registry_write_enabled(stage: str) -> bool:
    return normalize_phase4_5_rollout_stage(stage) in {"4.5b", "4.5c"}


def derived_active_cas_required(stage: str) -> bool:
    return normalize_phase4_5_rollout_stage(stage) == "4.5c"


def derived_latest_projection_update_allowed(stage: str, mode: RunMode) -> bool:
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = (mode or "normal").strip().lower()
    if normalized_mode == "replay":
        return False
    if normalized_mode == "backfill":
        return normalized_stage in {"4.5a", "4.5b"}
    if normalized_mode == "reconcile":
        return normalized_stage == "4.5c"
    if normalized_mode == "normal":
        return normalized_stage == "4.5c"
    return False


def derived_active_pointer_update_allowed(stage: str, mode: RunMode) -> bool:
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = (mode or "normal").strip().lower()
    if normalized_mode != "normal":
        return False
    return normalized_stage == "4.5c"


def resolve_phase4_5_rollout_stage(
    *,
    cli_override: str | None = None,
    env: Mapping[str, str] | None = None,
    mapping: dict[str, Any] | None = None,
) -> str:
    if cli_override:
        return normalize_phase4_5_rollout_stage(cli_override)
    env_map = env if env is not None else os.environ
    env_stage = str(env_map.get("PHASE4_5_ROLLOUT_STAGE") or "").strip()
    if env_stage:
        return normalize_phase4_5_rollout_stage(env_stage)
    if mapping is None:
        from stockradar.storage.mapping_catalog import load_mapping

        mapping = load_mapping()
    return normalize_phase4_5_rollout_stage(str(mapping.get("phase4_5_rollout_stage") or "off"))
