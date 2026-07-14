"""Phase 4 rollout stage helpers (Issue #93)."""
from __future__ import annotations

import os
from typing import Any, Final, Mapping

VALID_PHASE4_STAGES: Final[frozenset[str]] = frozenset({"4a", "4b", "4c"})


def normalize_phase4_rollout_stage(raw: str | None) -> str:
    stage = (raw or "4a").strip().lower()
    if stage not in VALID_PHASE4_STAGES:
        raise ValueError(f"invalid phase4 rollout stage: {raw!r}")
    return stage


def monthly_write_is_required(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4c"


def monthly_write_is_fatal(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4c"


def monthly_read_uses_supabase_primary(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) in {"4b", "4c"}


def monthly_read_allows_github_fallback(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4b"


def publish_commit_is_required(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4c"


def publish_commit_is_fatal(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4c"


def publish_dual_write_enabled(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) in {"4b", "4c"}


def runs_terminal_update_is_required(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) in {"4b", "4c"}


def runs_terminal_update_is_fatal(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) in {"4b", "4c"}


def monthly_shadow_write_enabled(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) == "4a"


def monthly_dual_write_enabled(stage: str) -> bool:
    return normalize_phase4_rollout_stage(stage) in {"4b", "4c"}


def resolve_phase4_rollout_stage(
    *,
    cli_override: str | None = None,
    env: Mapping[str, str] | None = None,
    mapping: dict[str, Any] | None = None,
) -> str:
    if cli_override:
        return normalize_phase4_rollout_stage(cli_override)
    env_map = env if env is not None else os.environ
    env_stage = str(env_map.get("PHASE4_ROLLOUT_STAGE") or "").strip()
    if env_stage:
        return normalize_phase4_rollout_stage(env_stage)
    if mapping is None:
        from stockradar.storage.mapping_catalog import load_mapping

        mapping = load_mapping()
    return normalize_phase4_rollout_stage(str(mapping.get("phase4_rollout_stage") or "4a"))
