"""Derived generation writer job orchestration (Phase 4.5)."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Callable

from stockradar.storage.derived_adapters import generation_store_from_env, r2_store_from_env
from stockradar.storage.derived_generation import (
    BeginGenerationRequest,
    GenerationConflictError,
    GenerationNotFoundError,
    GenerationStatus,
    MetricGenerationPort,
    SourceRunIdentity,
    profile_allows_latest,
    profile_allows_series,
    resolve_artifact_profile,
)
from stockradar.storage.derived_snapshot import (
    build_snapshot_manifest_bytes,
    build_snapshot_parquet_bytes,
    build_snapshot_rows,
    compute_object_sha256,
    compute_snapshot_logical_digest,
    snapshot_content_type,
)
from stockradar.storage.derived_series import (
    SERIES_GZIP_CONTENT_TYPE,
    build_series_canonical_bytes,
    gzip_series_bytes,
)
from stockradar.storage.phase4_5_rollout import (
    DerivedArtifact,
    PreflightResult,
    ResolveResult,
    ResolvedMetricSet,
    SetResolutionContext,
    object_key_for,
    preflight_derived_write,
    prefix_for,
    resolve_metric_set_version_id,
    validate_resolved_set_for_mode,
    write_allowed,
)
from stockradar.storage.r2_object_store import (
    R2ObjectAlreadyExistsError,
    R2ObjectStorePort,
)


@dataclass(frozen=True)
class SnapshotInput:
    metric_keys_ordered: list[str]
    metric_types: dict[str, str]
    values_by_instrument: dict[str, dict[str, Any]]
    layer1_input_fingerprint: str


@dataclass(frozen=True)
class DerivedGenerationRequest:
    stage: str
    mode: str
    trade_date: str
    repository: str
    workflow: str
    github_run_id: int
    metric_set_version_id: str | None = None
    active_metric_set_id: str | None = None
    lifecycle_status: str = "shadow"
    is_active: bool = False
    is_current_latest_trade_date: bool = False
    expected_old_digest: str | None = None
    writer_workflow: str = "derived_writer.yml"


@dataclass(frozen=True)
class DerivedGenerationResult:
    status: str
    skipped: bool = False
    exit_code: int = 0
    generation_id: str | None = None
    logical_digest: str | None = None
    object_keys: tuple[str, ...] = ()
    reason: str | None = None




def build_default_series_builders(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values_by_instrument: dict[str, dict[str, object]],
    prefixes,
    generation_id: str,
) -> list[Callable[[], tuple[dict[str, Any], bytes, str]]]:
    """Shadow series builders: one gzip object per instrument for trade_date year."""
    year = int(trade_date[:4])
    builders: list[Callable[[], tuple[dict[str, Any], bytes, str]]] = []

    for instrument_code in sorted(values_by_instrument):
        values = values_by_instrument[instrument_code]
        series = {
            key: [values.get(key)]
            for key in metric_keys_ordered
        }

        def _builder(
            instrument_code: str = instrument_code,
            series: dict[str, list[object]] = series,
        ) -> tuple[dict[str, Any], bytes, str]:
            canonical = build_series_canonical_bytes(
                instrument_code=instrument_code,
                year=year,
                dates=[trade_date],
                series=series,
                flags=[{}],
            )
            content = gzip_series_bytes(canonical)
            byte_sha = compute_object_sha256(content)
            logical_digest = compute_object_sha256(canonical)
            object_key = object_key_for(
                prefixes=prefixes,
                object_kind=DerivedArtifact.SERIES,
                instrument_code=instrument_code,
                year=year,
                generation_uuid=generation_id,
                object_sha256=byte_sha,
            )
            return (
                {
                    "object_kind": "series",
                    "object_key": object_key,
                    "logical_digest": logical_digest,
                    "instrument_code": instrument_code,
                    "series_year": year,
                },
                content,
                SERIES_GZIP_CONTENT_TYPE,
            )

        builders.append(_builder)
    return builders

def run_derived_generation(
    request: DerivedGenerationRequest,
    *,
    snapshot_input: SnapshotInput,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    series_builders: list[Callable[[], tuple[dict[str, Any], bytes, str]]] | None = None,
    latest_rows: list[dict[str, Any]] | None = None,
) -> DerivedGenerationResult:
    """
    Orchestrate Phase A→B→C and generation begin → reserve → put → commit.

    ``series_builders`` each return (register kwargs sans generation_id, content bytes, content_type).
    """
    preflight = preflight_derived_write(request.stage, request.mode)
    if preflight == PreflightResult.SKIP0:
        return DerivedGenerationResult(status="skipped", skipped=True, exit_code=0, reason="preflight_skip0")
    if preflight == PreflightResult.EXIT2:
        return DerivedGenerationResult(status="error", exit_code=2, reason="preflight_exit2")

    resolve_result, resolved_id = resolve_metric_set_version_id(
        stage=request.stage,
        mode=request.mode,
        metric_set_version_id=request.metric_set_version_id,
        ctx=SetResolutionContext(active_metric_set_id=request.active_metric_set_id),
    )
    if resolve_result == ResolveResult.SKIP0:
        return DerivedGenerationResult(status="skipped", skipped=True, exit_code=0, reason="resolve_skip0")
    if resolve_result in {ResolveResult.EXIT2, ResolveResult.FLAG_REQUIRED, ResolveResult.FLAG_MUST_MATCH_ACTIVE}:
        return DerivedGenerationResult(status="error", exit_code=2, reason=f"resolve_{resolve_result.value}")
    if resolve_result == ResolveResult.NO_RESOLVE_REPLAY:
        return DerivedGenerationResult(status="skipped", skipped=True, exit_code=0, reason="replay_no_write")
    if not resolved_id:
        return DerivedGenerationResult(status="error", exit_code=2, reason="resolve_missing_uuid")

    resolved = ResolvedMetricSet(
        metric_set_version_id=resolved_id,
        lifecycle_status=request.lifecycle_status,
        is_active=request.is_active,
    )
    if not validate_resolved_set_for_mode(
        stage=request.stage,
        mode=request.mode,
        resolved=resolved,
        ctx=SetResolutionContext(active_metric_set_id=request.active_metric_set_id),
    ):
        return DerivedGenerationResult(status="error", exit_code=2, reason="resolved_set_invalid")

    if not write_allowed(
        stage=request.stage,
        mode=request.mode,
        set_is_active=request.is_active,
        set_lifecycle=request.lifecycle_status,
        artifact=DerivedArtifact.SNAPSHOT,
    ):
        return DerivedGenerationResult(status="error", exit_code=2, reason="write_not_allowed_snapshot")

    profile = resolve_artifact_profile(
        stage=request.stage,
        mode=request.mode,
        is_current_latest_trade_date=request.is_current_latest_trade_date,
    )
    if profile_allows_series(profile.value) and not write_allowed(
        stage=request.stage,
        mode=request.mode,
        set_is_active=request.is_active,
        set_lifecycle=request.lifecycle_status,
        artifact=DerivedArtifact.SERIES,
    ):
        return DerivedGenerationResult(status="error", exit_code=2, reason="write_not_allowed_series")

    rows = build_snapshot_rows(
        trade_date=request.trade_date,
        metric_set_version_id=resolved_id,
        metric_keys_ordered=snapshot_input.metric_keys_ordered,
        metric_types=snapshot_input.metric_types,
        values_by_instrument=snapshot_input.values_by_instrument,
    )
    logical_digest, _canonical_bytes = compute_snapshot_logical_digest(
        trade_date=request.trade_date,
        metric_set_version_id=resolved_id,
        rows=rows,
    )
    snapshot_bytes = build_snapshot_parquet_bytes(trade_date=request.trade_date, rows=rows)
    snapshot_sha = compute_object_sha256(snapshot_bytes)
    prefixes = prefix_for(resolved_id)

    source = SourceRunIdentity(
        repository=request.repository,
        workflow=request.workflow,
        github_run_id=request.github_run_id,
        metric_set_version_id=resolved_id,
        trade_date=request.trade_date,
        mode=request.mode,
    )
    begin_request = BeginGenerationRequest(
        source=source,
        artifact_profile=profile,
        expected_logical_digest=request.expected_old_digest,
        new_logical_digest=logical_digest,
    )
    try:
        generation = generation_store.begin_generation(begin_request)
    except GenerationConflictError as exc:
        return DerivedGenerationResult(status="error", exit_code=2, reason=str(exc))

    if generation.status == GenerationStatus.COMMITTED.value:
        return DerivedGenerationResult(
            status="skipped",
            skipped=True,
            exit_code=0,
            generation_id=generation.generation_id,
            logical_digest=logical_digest,
            reason="generation_already_committed",
        )

    generation_id = generation.generation_id
    object_keys: list[str] = []

    snapshot_key = object_key_for(
        prefixes=prefixes,
        object_kind=DerivedArtifact.SNAPSHOT,
        trade_date=request.trade_date,
        generation_uuid=generation_id,
        object_sha256=snapshot_sha,
        manifest=False,
    )
    try:
        generation_store.register_pending_object(
            generation_id=generation_id,
            object_kind="snapshot",
            object_key=snapshot_key,
            logical_digest=logical_digest,
            byte_sha256=snapshot_sha,
            size_bytes=len(snapshot_bytes),
            trade_date=request.trade_date,
            layer1_input_fingerprint=snapshot_input.layer1_input_fingerprint,
        )
        r2_store.put_create_only(
            snapshot_key,
            snapshot_bytes,
            content_type=snapshot_content_type(snapshot_bytes),
        )
        generation_store.mark_object_uploaded(
            generation_id=generation_id,
            object_key=snapshot_key,
            byte_sha256=snapshot_sha,
            size_bytes=len(snapshot_bytes),
        )
        object_keys.append(snapshot_key)
    except (GenerationConflictError, GenerationNotFoundError, R2ObjectAlreadyExistsError) as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return DerivedGenerationResult(status="error", exit_code=2, reason=str(exc), generation_id=generation_id)

    manifest_bytes = build_snapshot_manifest_bytes(
        trade_date=request.trade_date,
        metric_set_version_id=resolved_id,
        generation_id=generation_id,
        logical_digest=logical_digest,
        object_sha256=snapshot_sha,
        size_bytes=len(snapshot_bytes),
        layer1_input_fingerprint=snapshot_input.layer1_input_fingerprint,
        writer_workflow=request.writer_workflow,
    )
    manifest_sha = compute_object_sha256(manifest_bytes)
    manifest_key = object_key_for(
        prefixes=prefixes,
        object_kind=DerivedArtifact.SNAPSHOT,
        trade_date=request.trade_date,
        generation_uuid=generation_id,
        object_sha256=manifest_sha,
        manifest=True,
    )
    try:
        r2_store.put_create_only(
            manifest_key,
            manifest_bytes,
            content_type="application/json",
        )
        object_keys.append(manifest_key)
    except R2ObjectAlreadyExistsError as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return DerivedGenerationResult(
            status="error",
            exit_code=2,
            reason=str(exc),
            generation_id=generation_id,
        )

    if profile_allows_series(profile.value):
        if series_builders is None:
            series_builders = build_default_series_builders(
                trade_date=request.trade_date,
                metric_keys_ordered=snapshot_input.metric_keys_ordered,
                values_by_instrument=snapshot_input.values_by_instrument,
                prefixes=prefixes,
                generation_id=generation_id,
            )
    if profile_allows_series(profile.value) and series_builders:
        for builder in series_builders:
            register_kwargs, content, content_type = builder()
            byte_sha = compute_object_sha256(content)
            object_key = str(register_kwargs["object_key"])
            try:
                generation_store.register_pending_object(
                    generation_id=generation_id,
                    byte_sha256=byte_sha,
                    size_bytes=len(content),
                    **register_kwargs,
                )
                r2_store.put_create_only(object_key, content, content_type=content_type)
                generation_store.mark_object_uploaded(
                    generation_id=generation_id,
                    object_key=object_key,
                    byte_sha256=byte_sha,
                    size_bytes=len(content),
                )
                object_keys.append(object_key)
            except (GenerationConflictError, GenerationNotFoundError, R2ObjectAlreadyExistsError) as exc:
                generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
                return DerivedGenerationResult(
                    status="error",
                    exit_code=2,
                    reason=str(exc),
                    generation_id=generation_id,
                )

    if profile_allows_latest(profile.value) and latest_rows:
        for row in latest_rows:
            generation_store.stage_latest_observation(
                generation_id=generation_id,
                instrument_code=str(row["instrument_code"]),
                trade_date=str(row["trade_date"]),
                values_json=dict(row["values_json"]),
                logical_digest=str(row["logical_digest"]),
            )

    if profile_allows_latest(profile.value) and request.is_current_latest_trade_date and not latest_rows:
        generation_store.fail_generation(
            generation_id=generation_id,
            reason="latest_rows_required_for_current_trade_date",
        )
        return DerivedGenerationResult(
            status="error",
            exit_code=2,
            reason="latest_rows_required_for_current_trade_date",
            generation_id=generation_id,
        )

    generation_store.heartbeat(generation_id=generation_id)
    try:
        committed = generation_store.commit_generation(
            generation_id=generation_id,
            new_logical_digest=logical_digest,
            expected_old_digest=request.expected_old_digest,
        )
    except GenerationConflictError as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return DerivedGenerationResult(status="error", exit_code=2, reason=str(exc), generation_id=generation_id)

    if committed.status == "committed":
        return DerivedGenerationResult(
            status="ok",
            exit_code=0,
            generation_id=generation_id,
            logical_digest=logical_digest,
            object_keys=tuple(object_keys),
        )

    return DerivedGenerationResult(
        status="error",
        exit_code=2,
        generation_id=generation_id,
        logical_digest=logical_digest,
        object_keys=tuple(object_keys),
        reason=f"commit_incomplete:{committed.status}",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write one derived generation (Fake-friendly).")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--repository", default="local/test")
    parser.add_argument("--workflow", default="derived_writer.yml")
    parser.add_argument("--github-run-id", type=int, default=1)
    parser.add_argument("--metric-set-version-id")
    parser.add_argument("--active-metric-set-id")
    parser.add_argument("--lifecycle-status", default="shadow")
    parser.add_argument("--is-active", choices=("true", "false"), default="false")
    parser.add_argument("--layer1-input-fingerprint", required=True)
    parser.add_argument(
        "--snapshot-json",
        help="Path to JSON file: {instrument_code: {metric_key: value}}",
    )
    args = parser.parse_args(argv)

    if not args.snapshot_json:
        payload = {"status": "error", "reason": "snapshot_json_required_for_cli"}
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(2)

    with open(args.snapshot_json, encoding="utf-8") as handle:
        values_by_instrument = json.load(handle)

    snapshot_input = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values_by_instrument,
        layer1_input_fingerprint=args.layer1_input_fingerprint,
    )
    request = DerivedGenerationRequest(
        stage=args.stage,
        mode=args.mode,
        trade_date=args.trade_date,
        repository=args.repository,
        workflow=args.workflow,
        github_run_id=args.github_run_id,
        metric_set_version_id=args.metric_set_version_id,
        active_metric_set_id=args.active_metric_set_id,
        lifecycle_status=args.lifecycle_status,
        is_active=args.is_active.lower() == "true",
        writer_workflow=args.workflow,
    )
    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store_from_env(),
        r2_store=r2_store_from_env(),
    )
    print(
        json.dumps(
            {
                "status": result.status,
                "skipped": result.skipped,
                "generation_id": result.generation_id,
                "logical_digest": result.logical_digest,
                "object_keys": list(result.object_keys),
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
