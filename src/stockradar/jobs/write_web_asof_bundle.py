"""Build and (optionally) commit Track D as-of view bundles.

Live daily stays mapping-gated until migration 020 is applied (U-3).
This module does not activate metric_set CAS.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from stockradar.storage.derived_generation import (
    ArtifactProfile,
    BeginGenerationRequest,
    GenerationConflictError,
    GenerationStatus,
    MetricGenerationPort,
    SourceRunIdentity,
    WEB_ASOF_EXPECTED_OBJECT_COUNT,
    compute_object_set_digest,
    expected_derived_object_count,
)
from stockradar.storage.r2_object_store import R2ObjectStorePort
from stockradar.storage.web_asof_bundle import (
    AXIS_LEN,
    BENCHMARKS,
    OPTIONAL_LAST_BAR_KEYS,
    ROW_METRIC_KEYS,
    SCHEMA_ID,
    SERIES_METRIC_KEYS,
    GZIP_MAX_BYTES,
    gzip_bundle_bytes,
    object_key,
    physical_bundle_object_key,
    physical_manifest_object_key,
    sha256_hex,
    sma75_cas_allowed,
    validate_web_asof_bundle,
)

WEB_ASOF_SOURCE_WORKFLOW = "daily.yml#write_web_asof"
BENCH_SUFFIXED_METRICS: tuple[str, ...] = tuple(
    key for key in ROW_METRIC_KEYS if key != "z_turnover_60"
)
OPTIONAL_SCALAR_KEYS: tuple[str, ...] = (
    "turnover_ma_ratio_60",
    "price_change_pct",
    "perfect_order_days",
)
OPTIONAL_BENCH_KEYS: tuple[str, ...] = tuple(
    key
    for key in OPTIONAL_LAST_BAR_KEYS
    if key not in OPTIONAL_SCALAR_KEYS
)
NEWS_SLOTS: tuple[tuple[str, str], ...] = (
    ("event_news_1_title", "event_news_1_url"),
    ("event_news_2_title", "event_news_2_url"),
    ("event_news_3_title", "event_news_3_url"),
)
IDENTITY_COPY_KEYS: tuple[str, ...] = (
    "price_text",
    "research_prompt_block",
    "candle_labels",
    "link_kabutan",
    "link_kabutan_chart",
    "link_kabutan_news",
    "link_buffett",
    "link_minkabu",
    "link_yahoo",
)
GZIP_CONTENT_TYPE = "application/gzip"
JSON_CONTENT_TYPE = "application/json"
BUNDLE_FLOAT_DECIMALS = 6


def _num_or_null(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return round(number, BUNDLE_FLOAT_DECIMALS)


def project_csv_row(
    csv_row: Mapping[str, Any],
    *,
    bench: str,
    as_of: str,
) -> dict[str, Any]:
    """Map a suffixed last-bar CSV row to unsuffixed bundle keys.

    News and identity fields copy only when the CSV row date equals ``as_of``.
    Previous-calendar fill is forbidden.
    """
    code = str(csv_row.get("code") or "").strip().zfill(4)
    row_date = str(csv_row.get("date") or csv_row.get("trade_date") or "").strip()
    same_asof = row_date == as_of
    out: dict[str, Any] = {
        "code": code,
        "name": str(csv_row.get("name") or ""),
        "z_turnover_60": _num_or_null(csv_row.get("z_turnover_60")),
    }
    for key in BENCH_SUFFIXED_METRICS:
        out[key] = _num_or_null(csv_row.get(f"{key}_{bench}"))
    for key in OPTIONAL_SCALAR_KEYS:
        out[key] = _num_or_null(csv_row.get(key))
    for key in OPTIONAL_BENCH_KEYS:
        out[key] = _num_or_null(csv_row.get(f"{key}_{bench}"))
    if same_asof:
        items: list[dict[str, str]] = []
        for title_col, url_col in NEWS_SLOTS:
            title = csv_row.get(title_col)
            if title is None or not str(title).strip():
                continue
            item: dict[str, str] = {"title": str(title).strip()}
            url = csv_row.get(url_col)
            if url is not None and str(url).strip():
                item["url"] = str(url).strip()
            items.append(item)
        out["event_news_bundle"] = items or None
        for ident in IDENTITY_COPY_KEYS:
            if ident in csv_row:
                raw = csv_row.get(ident)
                out[ident] = None if raw is None or str(raw).strip() == "" else raw
    else:
        out["event_news_bundle"] = None
    return out


def window_series_to_axis(
    dates: list[str],
    series_by_key: Mapping[str, list[Any]],
    axis_dates: list[str],
    *,
    bench: str,
) -> dict[str, list[Any]]:
    """Align a committed series window to the 60-day as-of axis; missing dates are null."""
    by_date = {str(d): i for i, d in enumerate(dates)}
    out: dict[str, list[Any]] = {}
    for unsuffixed in SERIES_METRIC_KEYS:
        src = unsuffixed if unsuffixed == "z_turnover_60" else f"{unsuffixed}_{bench}"
        if src not in series_by_key and unsuffixed in series_by_key:
            src = unsuffixed
        values = list(series_by_key.get(src) or [])
        window: list[Any] = []
        for day in axis_dates:
            idx = by_date.get(str(day))
            if idx is None or idx >= len(values):
                window.append(None)
            else:
                window.append(_num_or_null(values[idx]))
        out[unsuffixed] = window
    return out


def build_web_asof_bundle_payload(
    *,
    as_of: str,
    benchmark: str,
    metric_set_version_id: str,
    set_fingerprint: str,
    axis_dates: list[str],
    rows: list[Mapping[str, Any]],
    series: Mapping[str, Mapping[str, list[Any]]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "as_of": as_of,
        "benchmark": benchmark.strip().lower(),
        "metric_set_version_id": metric_set_version_id.strip().lower(),
        "set_fingerprint": set_fingerprint.strip().lower(),
        "axis_dates": list(axis_dates),
        "rows": [dict(row) for row in rows],
        "series": {str(code): dict(values) for code, values in series.items()},
    }
    validate_web_asof_bundle(payload)
    return payload


def encode_web_asof_bundle(payload: Mapping[str, Any]) -> tuple[bytes, str, str]:
    validate_web_asof_bundle(payload)
    blob = gzip_bundle_bytes(payload)
    key = object_key(
        metric_set_version_id=str(payload["metric_set_version_id"]),
        benchmark=str(payload["benchmark"]),
        as_of=str(payload["as_of"]),
    )
    return blob, key, sha256_hex(blob)


def build_web_asof_manifest(
    *,
    as_of: str,
    metric_set_version_id: str,
    set_fingerprint: str,
    objects: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_id": "web_asof_manifest_v1",
        "as_of": as_of,
        "metric_set_version_id": metric_set_version_id.strip().lower(),
        "set_fingerprint": set_fingerprint.strip().lower(),
        "objects": [dict(item) for item in objects],
    }


@dataclass(frozen=True)
class WebAsofGenerationRequest:
    as_of: str
    metric_set_version_id: str
    set_fingerprint: str
    repository: str
    github_run_id: int
    payloads: Mapping[str, Mapping[str, Any]]
    workflow: str = WEB_ASOF_SOURCE_WORKFLOW
    mode: str = "normal"


@dataclass(frozen=True)
class WebAsofGenerationResult:
    status: str
    exit_code: int
    generation_id: str | None = None
    reason: str | None = None
    object_keys: tuple[str, ...] = ()
    skipped: bool = False


def _sma75_values(payload: Mapping[str, Any]) -> list[Any]:
    return [row.get("rs_sma75") for row in payload.get("rows") or [] if isinstance(row, dict)]


def run_web_asof_generation(
    request: WebAsofGenerationRequest,
    *,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
) -> WebAsofGenerationResult:
    benches = {str(name).strip().lower() for name in request.payloads}
    if benches != set(BENCHMARKS):
        return WebAsofGenerationResult(
            status="error",
            exit_code=2,
            reason="payloads must include topix and nikkei",
        )
    encoded: dict[str, tuple[bytes, str, dict[str, Any]]] = {}
    for bench in ("topix", "nikkei"):
        payload = dict(request.payloads[bench])
        validate_web_asof_bundle(payload)
        if str(payload["as_of"]) != request.as_of:
            return WebAsofGenerationResult(
                status="error",
                exit_code=2,
                reason=f"{bench} as_of mismatch",
            )
        if str(payload["metric_set_version_id"]).strip().lower() != request.metric_set_version_id.strip().lower():
            return WebAsofGenerationResult(
                status="error",
                exit_code=2,
                reason=f"{bench} metric_set_version_id mismatch",
            )
        if not sma75_cas_allowed(_sma75_values(payload)):
            return WebAsofGenerationResult(
                status="error",
                exit_code=2,
                reason=f"{bench} rs_sma75 non-null rate below SMA75_NON_NULL_RATE_MIN",
            )
        blob = gzip_bundle_bytes(payload)
        if len(blob) >= GZIP_MAX_BYTES:
            return WebAsofGenerationResult(
                status="error",
                exit_code=2,
                reason=f"{bench} gzip exceeds GZIP_MAX_BYTES",
            )
        encoded[bench] = (blob, sha256_hex(blob), payload)

    source = SourceRunIdentity(
        repository=request.repository,
        workflow=request.workflow,
        github_run_id=request.github_run_id,
        metric_set_version_id=request.metric_set_version_id,
        trade_date=request.as_of,
        mode=request.mode,
    )
    begin = BeginGenerationRequest(
        source=source,
        artifact_profile=ArtifactProfile.WEB_ASOF,
        expected_object_count=expected_derived_object_count(
            profile=ArtifactProfile.WEB_ASOF,
            instrument_count=0,
        ),
    )
    try:
        generation = generation_store.begin_generation(begin)
    except GenerationConflictError as exc:
        return WebAsofGenerationResult(status="error", exit_code=2, reason=str(exc))
    if generation.status == GenerationStatus.COMMITTED.value:
        return WebAsofGenerationResult(
            status="skipped",
            exit_code=0,
            generation_id=generation.generation_id,
            reason="generation_already_committed",
            skipped=True,
        )

    generation_id = generation.generation_id
    object_keys: list[str] = []
    manifest_objects: list[dict[str, Any]] = []
    try:
        for bench in ("topix", "nikkei"):
            blob, digest, payload = encoded[bench]
            key = physical_bundle_object_key(
                metric_set_version_id=request.metric_set_version_id,
                benchmark=bench,
                as_of=request.as_of,
                generation_id=generation_id,
                digest=digest,
            )
            generation_store.register_pending_object(
                generation_id=generation_id,
                object_kind="web_asof_bundle",
                object_key=key,
                logical_digest=digest,
                byte_sha256=digest,
                size_bytes=len(blob),
                trade_date=request.as_of,
                benchmark=bench,
            )
            r2_store.put_create_only(key, blob, content_type=GZIP_CONTENT_TYPE)
            generation_store.mark_object_uploaded(
                generation_id=generation_id,
                object_key=key,
                byte_sha256=digest,
                size_bytes=len(blob),
            )
            object_keys.append(key)
            manifest_objects.append(
                {
                    "benchmark": bench,
                    "object_key": key,
                    "byte_sha256": digest,
                    "size_bytes": len(blob),
                    "schema_id": payload["schema_id"],
                }
            )

        manifest = build_web_asof_manifest(
            as_of=request.as_of,
            metric_set_version_id=request.metric_set_version_id,
            set_fingerprint=request.set_fingerprint,
            objects=manifest_objects,
        )
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        manifest_digest = sha256_hex(manifest_bytes)
        manifest_key = physical_manifest_object_key(
            metric_set_version_id=request.metric_set_version_id,
            as_of=request.as_of,
            generation_id=generation_id,
            digest=manifest_digest,
        )
        generation_store.register_pending_object(
            generation_id=generation_id,
            object_kind="web_asof_manifest",
            object_key=manifest_key,
            logical_digest=manifest_digest,
            byte_sha256=manifest_digest,
            size_bytes=len(manifest_bytes),
            trade_date=request.as_of,
        )
        r2_store.put_create_only(manifest_key, manifest_bytes, content_type=JSON_CONTENT_TYPE)
        generation_store.mark_object_uploaded(
            generation_id=generation_id,
            object_key=manifest_key,
            byte_sha256=manifest_digest,
            size_bytes=len(manifest_bytes),
        )
        object_keys.append(manifest_key)

        if len(object_keys) != WEB_ASOF_EXPECTED_OBJECT_COUNT:
            raise GenerationConflictError("web_asof object count mismatch before commit")

        generation_store.set_expected_object_set_digest(
            generation_id=generation_id,
            expected_object_set_digest=compute_object_set_digest(object_keys),
        )
        committed = generation_store.commit_generation(
            generation_id=generation_id,
            new_logical_digest=compute_object_set_digest(object_keys),
        )
    except Exception as exc:
        generation_store.fail_generation(generation_id=generation_id, reason=str(exc))
        return WebAsofGenerationResult(
            status="error",
            exit_code=2,
            generation_id=generation_id,
            reason=str(exc),
        )

    if committed.status != GenerationStatus.COMMITTED.value:
        return WebAsofGenerationResult(
            status="error",
            exit_code=2,
            generation_id=generation_id,
            reason=f"unexpected status {committed.status!r}",
        )
    return WebAsofGenerationResult(
        status="ok",
        exit_code=0,
        generation_id=generation_id,
        object_keys=tuple(object_keys),
    )


__all__ = [
    "AXIS_LEN",
    "ROW_METRIC_KEYS",
    "SERIES_METRIC_KEYS",
    "WEB_ASOF_SOURCE_WORKFLOW",
    "WebAsofGenerationRequest",
    "WebAsofGenerationResult",
    "build_web_asof_bundle_payload",
    "build_web_asof_manifest",
    "encode_web_asof_bundle",
    "project_csv_row",
    "run_web_asof_generation",
    "window_series_to_axis",
]
