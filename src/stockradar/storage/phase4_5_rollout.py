"""Phase 4.5 derived writer rollout helpers — Phase A→B→C SSOT (Issue #93)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Mapping

VALID_PHASE4_5_STAGES: Final[frozenset[str]] = frozenset({"off", "4.5a", "4.5b", "4.5c"})

RunMode = str  # normal | replay | backfill | reconcile | series_seed | series_repair


class DerivedArtifact(str, Enum):
    SNAPSHOT = "snapshot"
    SERIES = "series"
    GENERATION_INDEX = "generation_index"
    LATEST = "latest"


class PreflightResult(str, Enum):
    SKIP0 = "skip0"
    EXIT2 = "exit2"
    CONTINUE = "continue"


class ResolveResult(str, Enum):
    SKIP0 = "skip0"
    EXIT2 = "exit2"
    NO_RESOLVE_REPLAY = "no_resolve_replay"
    USE_UUID = "use_uuid"
    RESOLVE_ACTIVE = "resolve_active"
    FLAG_REQUIRED = "flag_required"
    FLAG_MUST_MATCH_ACTIVE = "flag_must_match_active"


@dataclass(frozen=True)
class DerivedPrefixes:
    snapshot_prefix: str
    series_prefix: str


@dataclass(frozen=True)
class ResolvedMetricSet:
    metric_set_version_id: str
    lifecycle_status: str
    is_active: bool


@dataclass(frozen=True)
class SetResolutionContext:
    active_metric_set_id: str | None = None


def normalize_phase4_5_rollout_stage(raw: str | None) -> str:
    stage = (raw or "off").strip().lower()
    if stage not in VALID_PHASE4_5_STAGES:
        raise ValueError(f"invalid phase4_5 rollout stage: {raw!r}")
    return stage


def normalize_run_mode(raw: str | None) -> RunMode:
    mode = (raw or "normal").strip().lower()
    if mode not in {
        "normal",
        "replay",
        "backfill",
        "reconcile",
        "series_seed",
        "series_repair",
    }:
        raise ValueError(f"invalid run mode: {raw!r}")
    return mode


def preflight_derived_write(stage: str, mode: RunMode) -> PreflightResult:
    """Phase A — set metadata not required."""
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = normalize_run_mode(mode)
    if normalized_stage == "off":
        return PreflightResult.SKIP0
    if normalized_mode == "replay":
        return PreflightResult.SKIP0
    if normalized_mode in {"series_seed", "series_repair"}:
        return (
            PreflightResult.CONTINUE
            if normalized_stage == "4.5c"
            else PreflightResult.EXIT2
        )
    if normalized_mode == "reconcile" and normalized_stage in {"4.5a", "4.5b"}:
        return PreflightResult.EXIT2
    return PreflightResult.CONTINUE


def resolve_metric_set_version_id(
    *,
    stage: str,
    mode: RunMode,
    metric_set_version_id: str | None = None,
    ctx: SetResolutionContext | None = None,
    lifecycle_status: str | None = None,
) -> tuple[ResolveResult, str | None]:
    """
    Phase B — single algorithm rule 0→5.

    Returns (result, uuid). Caller maps result to exit codes / validation.
    """
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = normalize_run_mode(mode)
    context = ctx or SetResolutionContext()

    # rule 0
    if normalized_stage == "off":
        return ResolveResult.SKIP0, None
    # rule 1
    if normalized_mode == "replay":
        return ResolveResult.NO_RESOLVE_REPLAY, None
    # rule 2 — explicit flag
    if metric_set_version_id:
        return ResolveResult.USE_UUID, metric_set_version_id.strip().lower()
    # rule 3
    if normalized_mode == "backfill" or (
        normalized_stage in {"4.5a", "4.5b"} and normalized_mode == "normal"
    ):
        return ResolveResult.FLAG_REQUIRED, None
    # rule 4
    if normalized_mode == "normal" and normalized_stage == "4.5c":
        active = context.active_metric_set_id
        if not active:
            return ResolveResult.EXIT2, None
        return ResolveResult.RESOLVE_ACTIVE, active
    if normalized_mode in {"series_seed", "series_repair"}:
        if normalized_stage != "4.5c":
            return ResolveResult.EXIT2, None
        active = context.active_metric_set_id
        if not active:
            return ResolveResult.EXIT2, None
        return ResolveResult.RESOLVE_ACTIVE, active
    # rule 5
    if normalized_mode == "reconcile":
        if normalized_stage != "4.5c":
            return ResolveResult.EXIT2, None
        return ResolveResult.FLAG_MUST_MATCH_ACTIVE, None
    return ResolveResult.EXIT2, None


def validate_resolved_set_for_mode(
    *,
    stage: str,
    mode: RunMode,
    resolved: ResolvedMetricSet,
    ctx: SetResolutionContext | None = None,
) -> bool:
    """Lifecycle/active rules after Phase B resolution."""
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = normalize_run_mode(mode)
    context = ctx or SetResolutionContext()
    lifecycle = resolved.lifecycle_status
    active_id = context.active_metric_set_id

    if normalized_mode in {"series_seed", "series_repair"}:
        if normalized_stage != "4.5c":
            return False
        if active_id and resolved.metric_set_version_id != active_id:
            return False
        return lifecycle == "active" and resolved.is_active
    if normalized_mode == "reconcile":
        if normalized_stage != "4.5c":
            return False
        if active_id and resolved.metric_set_version_id != active_id:
            return False
        return lifecycle == "active" and resolved.is_active
    if normalized_mode == "backfill" or normalized_stage in {"4.5a", "4.5b"}:
        return lifecycle == "shadow" and not resolved.is_active
    if normalized_mode == "normal" and normalized_stage == "4.5c":
        return lifecycle == "active" and resolved.is_active
    return False


def write_allowed(
    *,
    stage: str,
    mode: RunMode,
    set_is_active: bool,
    set_lifecycle: str,
    artifact: DerivedArtifact | str,
) -> bool:
    """Phase C — resolved set metadata required."""
    normalized_stage = normalize_phase4_5_rollout_stage(stage)
    normalized_mode = normalize_run_mode(mode)
    art = DerivedArtifact(artifact) if isinstance(artifact, str) else artifact
    lifecycle = set_lifecycle.strip().lower()

    if normalized_mode == "replay":
        return False
    if normalized_stage == "off":
        return False

    shadow_ok = lifecycle == "shadow" and not set_is_active
    active_ok = lifecycle == "active" and set_is_active

    if normalized_mode in {"series_seed", "series_repair"}:
        if normalized_stage != "4.5c" or not active_ok:
            return False
        return art in {
            DerivedArtifact.SERIES,
            DerivedArtifact.GENERATION_INDEX,
        }

    if normalized_mode == "backfill":
        if not shadow_ok:
            return False
        if art == DerivedArtifact.LATEST:
            return False
        if art == DerivedArtifact.SERIES:
            return normalized_stage in {"4.5b", "4.5c"}
        if art in {DerivedArtifact.SNAPSHOT, DerivedArtifact.GENERATION_INDEX}:
            return normalized_stage in {"4.5a", "4.5b", "4.5c"}
        return False

    if normalized_mode == "reconcile":
        if normalized_stage != "4.5c" or not active_ok:
            return False
        if art == DerivedArtifact.LATEST:
            return True  # caller restricts historical reconcile via profile
        return art in {
            DerivedArtifact.SNAPSHOT,
            DerivedArtifact.SERIES,
            DerivedArtifact.GENERATION_INDEX,
        }

    # normal
    if normalized_stage == "4.5a":
        if not shadow_ok:
            return False
        return art in {DerivedArtifact.SNAPSHOT, DerivedArtifact.GENERATION_INDEX}
    if normalized_stage == "4.5b":
        if not shadow_ok:
            return False
        return art in {
            DerivedArtifact.SNAPSHOT,
            DerivedArtifact.SERIES,
            DerivedArtifact.GENERATION_INDEX,
        }
    if normalized_stage == "4.5c":
        if not active_ok:
            return False
        return True
    return False


def prefix_for(set_uuid: str) -> DerivedPrefixes:
    uid = set_uuid.strip()
    return DerivedPrefixes(
        snapshot_prefix=f"derived-snapshots/metric-set={uid}",
        series_prefix=f"derived-series/metric-set={uid}",
    )


def object_key_for(
    *,
    prefixes: DerivedPrefixes,
    object_kind: DerivedArtifact | str,
    trade_date: str | None = None,
    instrument_code: str | None = None,
    year: int | None = None,
    generation_uuid: str,
    object_sha256: str,
    manifest: bool = False,
) -> str:
    """Build immutable R2 object key (full byte SHA-256 required)."""
    kind = DerivedArtifact(object_kind) if isinstance(object_kind, str) else object_kind
    gen = generation_uuid.strip().lower()
    digest = object_sha256.strip().lower()
    if kind == DerivedArtifact.SNAPSHOT:
        if manifest:
            return (
                f"{prefixes.snapshot_prefix}/trade-date={trade_date}/"
                f"generation={gen}/manifest-sha256={digest}.json"
            )
        return (
            f"{prefixes.snapshot_prefix}/trade-date={trade_date}/"
            f"generation={gen}/indicators-sha256={digest}.parquet"
        )
    if kind == DerivedArtifact.SERIES:
        if manifest:
            return (
                f"{prefixes.series_prefix}/symbol={instrument_code}/year={year}/"
                f"generation={gen}/manifest-sha256={digest}.json"
            )
        return (
            f"{prefixes.series_prefix}/symbol={instrument_code}/year={year}/"
            f"generation={gen}/series-sha256={digest}.json.gz"
        )
    raise ValueError(f"object_key_for unsupported kind: {kind!r}")


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


# --- thin wrappers (legacy API; no independent truth tables) ---

def derived_writer_enabled(stage: str) -> bool:
    return preflight_derived_write(stage, "normal") != PreflightResult.SKIP0


def derived_shadow_snapshot_write_enabled(stage: str) -> bool:
    return write_allowed(
        stage=stage,
        mode="normal",
        set_is_active=False,
        set_lifecycle="shadow",
        artifact=DerivedArtifact.SNAPSHOT,
    )


def derived_shadow_series_write_enabled(stage: str) -> bool:
    return write_allowed(
        stage=stage,
        mode="normal",
        set_is_active=False,
        set_lifecycle="shadow",
        artifact=DerivedArtifact.SERIES,
    )


def derived_registry_write_enabled(stage: str) -> bool:
    return write_allowed(
        stage=stage,
        mode="normal",
        set_is_active=False,
        set_lifecycle="shadow",
        artifact=DerivedArtifact.GENERATION_INDEX,
    )


def derived_active_cas_required(stage: str) -> bool:
    """Job path: always False (ops-only CAS)."""
    return False


def derived_latest_projection_update_allowed(stage: str, mode: RunMode) -> bool:
    return write_allowed(
        stage=stage,
        mode=mode,
        set_is_active=True,
        set_lifecycle="active",
        artifact=DerivedArtifact.LATEST,
    )


def derived_active_pointer_update_allowed(stage: str, mode: RunMode) -> bool:
    """Job path: always False (ops-only CAS)."""
    return False
