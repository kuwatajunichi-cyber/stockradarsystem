"""Derived generation writer job orchestration (Phase 4.5)."""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    compute_object_set_digest,
    expected_derived_object_count,
    profile_allows_latest,
    profile_allows_series,
    resolve_artifact_profile,
)
from stockradar.storage.derived_snapshot import (
    DERIVED_WRITER_VERSION,
    build_snapshot_manifest_bytes,
    build_snapshot_parquet_bytes,
    build_snapshot_rows,
    compute_object_sha256,
    compute_snapshot_logical_digest,
    LATEST_FLAGS_KEY,
    flags_for_values,
    latest_values_json_with_flags,
    snapshot_content_type,
)
from stockradar.storage.derived_series import (
    SERIES_GZIP_CONTENT_TYPE,
    build_series_canonical_bytes,
    build_series_manifest_bytes,
    gunzip_series_bytes,
    gzip_series_bytes,
    merge_trade_date_into_series,
    parse_series_canonical_bytes,
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
    set_fingerprint: str = ""
    writer_version: str = DERIVED_WRITER_VERSION


DERIVED_SERIES_CHUNK_SIZE = 500
DEFAULT_DERIVED_R2_CONCURRENCY = 32


def resolve_r2_concurrency(raw: str | None = None) -> int:
    value = raw if raw is not None else os.environ.get('DERIVED_R2_CONCURRENCY')
    try:
        concurrency = int(str(value if value is not None else DEFAULT_DERIVED_R2_CONCURRENCY).strip() or DEFAULT_DERIVED_R2_CONCURRENCY)
    except ValueError:
        concurrency = DEFAULT_DERIVED_R2_CONCURRENCY
    return max(1, concurrency)


@dataclass(frozen=True)
class DerivedGenerationResult:
    status: str
    skipped: bool = False
    exit_code: int = 0
    generation_id: str | None = None
    logical_digest: str | None = None
    object_keys: tuple[str, ...] = ()
    reason: str | None = None
    series_count: int = 0
    r2_concurrency: int = 1
    prefetch_elapsed_ms: int = 0
    put_elapsed_ms: int = 0
    rpc_elapsed_ms: int = 0




def build_accumulating_series_builders(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values_by_instrument: dict[str, dict[str, object]],
    prefixes,
    generation_id: str,
    metric_set_version_id: str,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    committed_series_keys: dict[str, str] | None = None,
) -> list[Callable[[], tuple[dict[str, Any], bytes, str]]]:
    """Series builders that merge trade_date into prior committed year series when present."""
    year = int(trade_date[:4])
    builders: list[Callable[[], tuple[dict[str, Any], bytes, str]]] = []

    for instrument_code in sorted(values_by_instrument):
        values = values_by_instrument[instrument_code]

        def _builder(
            instrument_code: str = instrument_code,
            values: dict[str, object] = values,
        ) -> tuple[dict[str, Any], bytes, str]:
            prior_dates: list[str] | None = None
            prior_series: dict[str, list[object]] | None = None
            prior_flags: list[dict[str, Any]] | None = None
            if committed_series_keys is not None:
                object_key = committed_series_keys.get(instrument_code)
            else:
                object_key = generation_store.get_committed_series_object_key(
                    metric_set_version_id=metric_set_version_id,
                    instrument_code=instrument_code,
                    series_year=year,
                )
            if object_key:
                gzip_bytes = r2_store.get_object(object_key)
                canonical_bytes = gunzip_series_bytes(gzip_bytes)
                prior_dates, prior_series, prior_flags = parse_series_canonical_bytes(
                    canonical_bytes
                )
            dates, series, flags = merge_trade_date_into_series(
                trade_date=trade_date,
                metric_keys_ordered=metric_keys_ordered,
                values=values,
                instrument_code=instrument_code,
                prior_dates=prior_dates,
                prior_series=prior_series,
                prior_flags=prior_flags,
            )
            canonical = build_series_canonical_bytes(
                instrument_code=instrument_code,
                year=year,
                dates=dates,
                series=series,
                flags=flags,
                metric_keys_ordered=metric_keys_ordered,
            )
            content = gzip_series_bytes(canonical)
            byte_sha = compute_object_sha256(content)
            logical_digest = compute_object_sha256(canonical)
            new_object_key = object_key_for(
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
                    "object_key": new_object_key,
                    "logical_digest": logical_digest,
                    "instrument_code": instrument_code,
                    "series_year": year,
                    "row_count": len(dates),
                },
                content,
                SERIES_GZIP_CONTENT_TYPE,
            )

        builders.append(_builder)
    return builders


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
            values: dict[str, object] = values,
        ) -> tuple[dict[str, Any], bytes, str]:
            canonical = build_series_canonical_bytes(
                instrument_code=instrument_code,
                year=year,
                dates=[trade_date],
                series=series,
                flags=[
                    flags_for_values(
                        instrument_code=instrument_code,
                        metric_keys_ordered=metric_keys_ordered,
                        metric_types={key: "float" for key in metric_keys_ordered},
                        values_by_key=values,
                    )
                ],
                metric_keys_ordered=metric_keys_ordered,
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
                    "row_count": 1,
                },
                content,
                SERIES_GZIP_CONTENT_TYPE,
            )

        builders.append(_builder)
    return builders


def _chunked_items(items: list[Any], size: int = DERIVED_SERIES_CHUNK_SIZE) -> list[list[Any]]:
    if size <= 0:
        raise ValueError('chunk size must be positive')
    return [items[i : i + size] for i in range(0, len(items), size)]


def _warm_r2_client(r2_store: R2ObjectStorePort) -> None:
    warm = getattr(r2_store, 'warm_client', None)
    if callable(warm):
        warm()


def _put_series_chunk_parallel(
    *,
    r2_store: R2ObjectStorePort,
    items: list[tuple[str, bytes, str]],
    concurrency: int,
) -> None:
    if not items:
        return
    workers = max(1, min(concurrency, len(items)))
    if workers == 1:
        for object_key, content, content_type in items:
            r2_store.put_create_only(object_key, content, content_type=content_type)
        return
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [
            executor.submit(r2_store.put_create_only, object_key, content, content_type=content_type)
            for object_key, content, content_type in items
        ]
        for fut in as_completed(futures):
            fut.result()
    except Exception:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=False)


def _prefetch_prior_gzip(
    *,
    r2_store: R2ObjectStorePort,
    committed_series_keys: dict[str, str],
    instrument_codes: list[str],
    concurrency: int,
) -> dict[str, bytes]:
    to_fetch = [
        (code, committed_series_keys[code])
        for code in instrument_codes
        if code in committed_series_keys
    ]
    if not to_fetch:
        return {}
    out: dict[str, bytes] = {}
    workers = max(1, min(concurrency, len(to_fetch)))
    if workers == 1:
        for code, key in to_fetch:
            out[code] = r2_store.get_object(key)
        return out
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            executor.submit(r2_store.get_object, key): code for code, key in to_fetch
        }
        for fut in as_completed(futures):
            code = futures[fut]
            out[code] = fut.result()
    except Exception:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=False)
    return out


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
    Series register kwargs must include ``row_count`` (trade-date count in the gzip body).
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
        expected_object_count=expected_derived_object_count(
            profile=profile,
            instrument_count=len(snapshot_input.values_by_instrument),
        ),
        expected_latest_set_digest=(
            compute_object_set_digest(list(snapshot_input.values_by_instrument))
            if profile_allows_latest(profile.value)
            else None
        ),
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
        object_size=len(snapshot_bytes),
        layer1_input_fingerprint=snapshot_input.layer1_input_fingerprint,
        writer_workflow=request.writer_workflow,
        set_fingerprint=request.set_fingerprint,
        source_github_run_id=request.github_run_id,
        row_count=len(rows),
        metric_keys_ordered=snapshot_input.metric_keys_ordered,
        mode=request.mode,
        writer_version=request.writer_version,
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
        generation_store.register_pending_object(
            generation_id=generation_id,
            object_kind="snapshot_manifest",
            object_key=manifest_key,
            logical_digest=logical_digest,
            byte_sha256=manifest_sha,
            size_bytes=len(manifest_bytes),
            trade_date=request.trade_date,
        )
        r2_store.put_create_only(
            manifest_key,
            manifest_bytes,
            content_type="application/json",
        )
        generation_store.mark_object_uploaded(
            generation_id=generation_id,
            object_key=manifest_key,
            byte_sha256=manifest_sha,
            size_bytes=len(manifest_bytes),
        )
        object_keys.append(manifest_key)
    except (GenerationConflictError, GenerationNotFoundError, R2ObjectAlreadyExistsError) as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return DerivedGenerationResult(
            status="error",
            exit_code=2,
            reason=str(exc),
            generation_id=generation_id,
        )

    r2_concurrency = resolve_r2_concurrency()
    series_count = 0
    prefetch_elapsed_ms = 0
    put_elapsed_ms = 0
    rpc_elapsed_ms = 0

    def _error_result(reason: str) -> DerivedGenerationResult:
        return DerivedGenerationResult(
            status="error",
            exit_code=2,
            reason=reason,
            generation_id=generation_id,
            series_count=series_count,
            r2_concurrency=r2_concurrency,
            prefetch_elapsed_ms=prefetch_elapsed_ms,
            put_elapsed_ms=put_elapsed_ms,
            rpc_elapsed_ms=rpc_elapsed_ms,
        )

    try:
        _warm_r2_client(r2_store)

        if profile_allows_series(profile.value):
            if series_builders is None:
                t0 = time.perf_counter()
                committed_series_keys = generation_store.list_committed_series_keys(
                    metric_set_version_id=resolved_id,
                    series_year=int(request.trade_date[:4]),
                )
                # Prefetch prior gzip for instruments that have a committed series.
                _ = _prefetch_prior_gzip(
                    r2_store=r2_store,
                    committed_series_keys=committed_series_keys,
                    instrument_codes=sorted(snapshot_input.values_by_instrument),
                    concurrency=r2_concurrency,
                )
                # Builders still call get_object; warm cache via committed index avoids list GET.
                # Re-fetch is avoided by injecting committed_series_keys; prior GET happens in builder.
                # To avoid double GET, replace builders path with cached prior bytes.
                prefetch_elapsed_ms = int((time.perf_counter() - t0) * 1000)
                prior_gzip = _
                series_builders = []
                year = int(request.trade_date[:4])
                metric_keys_ordered = snapshot_input.metric_keys_ordered

                def _make_builder(
                    instrument_code: str,
                    values: dict[str, object],
                    prior_bytes: bytes | None,
                ) -> Callable[[], tuple[dict[str, Any], bytes, str]]:
                    def _builder() -> tuple[dict[str, Any], bytes, str]:
                        prior_dates = prior_series = prior_flags = None
                        if prior_bytes is not None:
                            canonical_bytes = gunzip_series_bytes(prior_bytes)
                            prior_dates, prior_series, prior_flags = parse_series_canonical_bytes(
                                canonical_bytes
                            )
                        dates, series, flags = merge_trade_date_into_series(
                            trade_date=request.trade_date,
                            metric_keys_ordered=metric_keys_ordered,
                            values=values,
                            metric_types=snapshot_input.metric_types,
                            instrument_code=instrument_code,
                            prior_dates=prior_dates,
                            prior_series=prior_series,
                            prior_flags=prior_flags,
                        )
                        canonical = build_series_canonical_bytes(
                            instrument_code=instrument_code,
                            year=year,
                            dates=dates,
                            series=series,
                            flags=flags,
                            metric_keys_ordered=metric_keys_ordered,
                        )
                        content = gzip_series_bytes(canonical)
                        byte_sha = compute_object_sha256(content)
                        logical = compute_object_sha256(canonical)
                        new_object_key = object_key_for(
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
                                "object_key": new_object_key,
                                "logical_digest": logical,
                                "instrument_code": instrument_code,
                                "series_year": year,
                                "row_count": len(dates),
                            },
                            content,
                            SERIES_GZIP_CONTENT_TYPE,
                        )

                    return _builder

                for instrument_code in sorted(snapshot_input.values_by_instrument):
                    series_builders.append(
                        _make_builder(
                            instrument_code,
                            snapshot_input.values_by_instrument[instrument_code],
                            prior_gzip.get(instrument_code),
                        )
                    )
            elif series_builders is not None:
                # Injected builders: still use batch + parallel PUT path below.
                pass

            prepared: list[tuple[dict[str, Any], bytes, str, str, int]] = []
            for builder in series_builders or []:
                register_kwargs, content, content_type = builder()
                byte_sha = compute_object_sha256(content)
                series_item = dict(register_kwargs)
                if "row_count" not in series_item:
                    raise ValueError("series builder must include row_count")
                row_count = int(series_item.pop("row_count"))
                prepared.append(
                    (
                        series_item,
                        content,
                        content_type,
                        byte_sha,
                        len(content),
                    )
                )
                instrument_code = str(series_item["instrument_code"])
                series_year = int(series_item["series_year"])
                series_manifest = build_series_manifest_bytes(
                    instrument_code=instrument_code,
                    year=series_year,
                    metric_set_version_id=resolved_id,
                    generation_id=generation_id,
                    logical_digest=str(series_item["logical_digest"]),
                    object_sha256=byte_sha,
                    object_size=len(content),
                    writer_workflow=request.writer_workflow,
                    set_fingerprint=request.set_fingerprint,
                    source_github_run_id=request.github_run_id,
                    row_count=row_count,
                    metric_keys_ordered=snapshot_input.metric_keys_ordered,
                    mode=request.mode,
                    writer_version=request.writer_version,
                )
                manifest_sha = compute_object_sha256(series_manifest)
                manifest_key = object_key_for(
                    prefixes=prefixes,
                    object_kind=DerivedArtifact.SERIES,
                    instrument_code=instrument_code,
                    year=series_year,
                    generation_uuid=generation_id,
                    object_sha256=manifest_sha,
                    manifest=True,
                )
                prepared.append(
                    (
                        {
                            "object_kind": "series_manifest",
                            "object_key": manifest_key,
                            "logical_digest": str(series_item["logical_digest"]),
                            "instrument_code": instrument_code,
                            "series_year": series_year,
                        },
                        series_manifest,
                        "application/json",
                        manifest_sha,
                        len(series_manifest),
                    )
                )
            series_count = sum(1 for item in prepared if item[0].get("object_kind") == "series")

            for chunk in _chunked_items(prepared, DERIVED_SERIES_CHUNK_SIZE):
                register_payload = []
                for register_kwargs, content, content_type, byte_sha, size_bytes in chunk:
                    item = dict(register_kwargs)
                    item["byte_sha256"] = byte_sha
                    item["size_bytes"] = size_bytes
                    register_payload.append(item)
                t_rpc = time.perf_counter()
                records = generation_store.register_pending_objects(
                    generation_id=generation_id,
                    objects=register_payload,
                )
                rpc_elapsed_ms += int((time.perf_counter() - t_rpc) * 1000)
                by_key = {rec.object_key: rec for rec in records}

                put_items = [
                    (str(register_kwargs["object_key"]), content, content_type)
                    for register_kwargs, content, content_type, _byte_sha, _size in chunk
                ]
                t_put = time.perf_counter()
                _put_series_chunk_parallel(
                    r2_store=r2_store,
                    items=put_items,
                    concurrency=r2_concurrency,
                )
                put_elapsed_ms += int((time.perf_counter() - t_put) * 1000)

                uploads = []
                for register_kwargs, _content, _ctype, byte_sha, size_bytes in chunk:
                    object_key = str(register_kwargs["object_key"])
                    rec = by_key.get(object_key)
                    if rec is None:
                        raise GenerationNotFoundError(
                            f"batch register missing object_key={object_key!r}"
                        )
                    uploads.append(
                        {
                            "object_id": rec.object_id,
                            "byte_sha256": byte_sha,
                            "size_bytes": size_bytes,
                        }
                    )
                    object_keys.append(object_key)
                t_rpc = time.perf_counter()
                generation_store.mark_objects_uploaded(
                    generation_id=generation_id,
                    uploads=uploads,
                )
                rpc_elapsed_ms += int((time.perf_counter() - t_rpc) * 1000)
                generation_store.heartbeat(generation_id=generation_id)

        if profile_allows_latest(profile.value) and latest_rows:
            enriched_latest: list[dict[str, Any]] = []
            for row in latest_rows:
                instrument_code = str(row["instrument_code"])
                raw_values = dict(row["values_json"])
                existing_flags = raw_values.pop(LATEST_FLAGS_KEY, None)
                flags = (
                    existing_flags
                    if isinstance(existing_flags, dict)
                    else flags_for_values(
                        instrument_code=instrument_code,
                        metric_keys_ordered=snapshot_input.metric_keys_ordered,
                        metric_types=snapshot_input.metric_types,
                        values_by_key=raw_values,
                    )
                )
                enriched_latest.append(
                    {
                        "instrument_code": instrument_code,
                        "trade_date": str(row["trade_date"]),
                        "values_json": latest_values_json_with_flags(
                            values=raw_values,
                            flags=flags,
                        ),
                        "logical_digest": str(row["logical_digest"]),
                    }
                )
            for chunk in _chunked_items(enriched_latest, DERIVED_SERIES_CHUNK_SIZE):
                t_rpc = time.perf_counter()
                generation_store.stage_latest_observations(
                    generation_id=generation_id,
                    rows=chunk,
                )
                rpc_elapsed_ms += int((time.perf_counter() - t_rpc) * 1000)
                generation_store.heartbeat(generation_id=generation_id)

        if profile_allows_latest(profile.value) and request.is_current_latest_trade_date and not latest_rows:
            generation_store.fail_generation(
                generation_id=generation_id,
                reason="latest_rows_required_for_current_trade_date",
            )
            return _error_result("latest_rows_required_for_current_trade_date")

        generation_store.heartbeat(generation_id=generation_id)
        generation_store.set_expected_object_set_digest(
            generation_id=generation_id,
            expected_object_set_digest=compute_object_set_digest(object_keys),
        )
        committed = generation_store.commit_generation(
            generation_id=generation_id,
            new_logical_digest=logical_digest,
            expected_old_digest=request.expected_old_digest,
        )
    except Exception as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return _error_result(str(exc))

    if committed.status == "committed":
        return DerivedGenerationResult(
            status="ok",
            exit_code=0,
            generation_id=generation_id,
            logical_digest=logical_digest,
            object_keys=tuple(object_keys),
            series_count=series_count,
            r2_concurrency=r2_concurrency,
            prefetch_elapsed_ms=prefetch_elapsed_ms,
            put_elapsed_ms=put_elapsed_ms,
            rpc_elapsed_ms=rpc_elapsed_ms,
        )

    return DerivedGenerationResult(
        status="error",
        exit_code=2,
        generation_id=generation_id,
        logical_digest=logical_digest,
        object_keys=tuple(object_keys),
        reason=f"commit_incomplete:{committed.status}",
        series_count=series_count,
        r2_concurrency=r2_concurrency,
        prefetch_elapsed_ms=prefetch_elapsed_ms,
        put_elapsed_ms=put_elapsed_ms,
        rpc_elapsed_ms=rpc_elapsed_ms,
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
