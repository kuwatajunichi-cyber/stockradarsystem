"""Dedicated series_only writer for ADR-005 series_seed / series_repair.

Does NOT call write_derived_generation / run_derived_generation (those require snapshot).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.metrics.registry_spec import (  # noqa: E402
    load_metric_set_spec,
    metric_set_is_series_seedable,
    require_seed_metric_input_contract,
)
from stockradar.storage.derived_generation import (  # noqa: E402
    ArtifactProfile,
    BeginGenerationRequest,
    MetricGenerationPort,
    SeriesCoordinateCAS,
    SourceRunIdentity,
    compute_object_set_digest,
    expected_derived_object_count,
    resolve_artifact_profile,
)
from stockradar.storage.derived_series import (  # noqa: E402
    SERIES_GZIP_CONTENT_TYPE,
    build_series_canonical_bytes,
    build_series_manifest_bytes,
    compute_object_sha256,
    gunzip_series_bytes,
    gzip_series_bytes,
    merge_missing_dates_only,
    parse_series_canonical_bytes,
)
from stockradar.storage.derived_snapshot import (  # noqa: E402
    DERIVED_WRITER_VERSION,
    dump_canonical_json,
    flags_for_values,
)
from stockradar.storage.phase4_5_rollout import (  # noqa: E402
    DerivedArtifact,
    normalize_run_mode,
    object_key_for,
    prefix_for,
    write_allowed,
)
from stockradar.storage.r2_object_store import R2ObjectStorePort  # noqa: E402
from stockradar.storage.series_seed import (  # noqa: E402
    classify_seed_trade_date_codes,
    series_only_expected_object_count,
    validate_series_repair_approver,
)
from stockradar.utils.yf_cache_long_history import fetch_long_history_bounded  # noqa: E402

DEFAULT_R2_CONCURRENCY = 32


def _r2_concurrency() -> int:
    raw = (
        os.environ.get("MNC_R2_CONCURRENCY", "").strip()
        or os.environ.get("DERIVED_R2_CONCURRENCY", "").strip()
        or str(DEFAULT_R2_CONCURRENCY)
    )
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_R2_CONCURRENCY
    return max(1, min(64, value))


@dataclass(frozen=True)
class SeriesOnlyWritePlan:
    request_id: str
    mode: str
    trade_date: str
    write_codes: tuple[str, ...]
    resolved_noop_codes: tuple[str, ...]
    expected_object_count: int
    artifact_profile: str


@dataclass
class ExistingSeriesState:
    """Committed year series state for seed CAS / merge."""

    dates_by_code: dict[str, list[str]] = field(default_factory=dict)
    series_by_code: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    flags_by_code: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    prior_digest_by_code: dict[str, str] = field(default_factory=dict)

    def prior_absent_by_code(self, codes: Sequence[str]) -> dict[str, bool]:
        return {code: code not in self.prior_digest_by_code for code in codes}


def plan_series_only_trade_date(
    *,
    request_id: str,
    mode: str,
    trade_date: str,
    candidate_codes: Sequence[str],
    existing_dates_by_code: Mapping[str, Sequence[str]],
    stage: str = "4.5c",
) -> SeriesOnlyWritePlan:
    normalized = normalize_run_mode(mode)
    if normalized not in {"series_seed", "series_repair"}:
        raise ValueError(f"series_only writer rejects mode {mode!r}")
    profile = resolve_artifact_profile(stage=stage, mode=normalized)
    if profile != ArtifactProfile.SERIES_ONLY:
        raise ValueError(f"expected SERIES_ONLY profile, got {profile}")
    if not write_allowed(
        stage=stage,
        mode=normalized,
        set_is_active=True,
        set_lifecycle="active",
        artifact="series",
    ):
        raise RuntimeError("series write not allowed for stage/mode")
    split = classify_seed_trade_date_codes(
        candidate_codes=candidate_codes,
        existing_dates_by_code=existing_dates_by_code,
        trade_date=trade_date,
    )
    write_codes = tuple(split["write"])
    noop = tuple(split["resolved_noop"])
    expected = series_only_expected_object_count(len(write_codes))
    # Keep in sync with derived_generation.expected_derived_object_count
    if write_codes:
        assert expected == expected_derived_object_count(
            profile=ArtifactProfile.SERIES_ONLY, instrument_count=len(write_codes)
        )
    return SeriesOnlyWritePlan(
        request_id=request_id,
        mode=normalized,
        trade_date=trade_date,
        write_codes=write_codes,
        resolved_noop_codes=noop,
        expected_object_count=expected,
        artifact_profile=profile.value,
    )


def ensure_seed_catalog_or_block() -> None:
    spec = load_metric_set_spec()
    require_seed_metric_input_contract(spec)
    if not metric_set_is_series_seedable(spec):
        raise RuntimeError("blocked:metric_not_series_seedable")


def build_begin_request_for_plan(
    *,
    plan: SeriesOnlyWritePlan,
    metric_set_version_id: str,
    github_run_id: int,
    repository: str = "local/stockradarsystem",
    prior_absent_by_code: Mapping[str, bool] | None = None,
    expected_prior_digest_by_code: Mapping[str, str] | None = None,
) -> BeginGenerationRequest:
    if plan.expected_object_count == 0:
        raise ValueError("no generation when expected_object_count is 0")
    coords: list[SeriesCoordinateCAS] = []
    prior_absent = prior_absent_by_code or {}
    digests = expected_prior_digest_by_code or {}
    year = int(str(plan.trade_date)[:4])
    for code in plan.write_codes:
        coords.append(
            SeriesCoordinateCAS(
                instrument_code=code,
                series_year=year,
                expected_prior_logical_digest=digests.get(code),
                prior_absent=bool(prior_absent.get(code, code not in digests)),
            )
        )
    return BeginGenerationRequest(
        source=SourceRunIdentity(
            repository=repository,
            workflow="monthly_new_core_backfill.yml",
            github_run_id=github_run_id,
            metric_set_version_id=metric_set_version_id,
            trade_date=plan.trade_date,
            mode=plan.mode,  # type: ignore[arg-type]
        ),
        artifact_profile=ArtifactProfile.SERIES_ONLY,
        expected_object_count=plan.expected_object_count,
        series_coordinates=tuple(coords),
        request_id=plan.request_id,
    )


def merge_seed_observation(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values: dict[str, Any],
    instrument_code: str,
    prior_dates: list[str] | None,
    prior_series: dict[str, list[Any]] | None,
    prior_flags: list[dict[str, Any]] | None,
) -> tuple[list[str], dict[str, list[Any]], list[dict[str, Any]], bool]:
    return merge_missing_dates_only(
        trade_date=trade_date,
        metric_keys_ordered=metric_keys_ordered,
        values=values,
        instrument_code=instrument_code,
        prior_dates=prior_dates,
        prior_series=prior_series,
        prior_flags=prior_flags,
    )


def fetch_bounded_layer1(
    *,
    required_input_start: datetime,
    coverage_end: datetime,
    fetch_chunk,
):
    return fetch_long_history_bounded(
        required_input_start=required_input_start,
        coverage_end=coverage_end,
        fetch_chunk=fetch_chunk,
    )


def _json_number_or_null(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
    except TypeError:
        pass
    try:
        # pandas / numpy scalars
        if hasattr(value, "item"):
            value = value.item()
    except Exception:
        pass
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_series_seed_delta_bytes(
    *,
    request_id: str,
    trade_date: str,
    metric_set_version_id: str,
    generation_id: str,
    object_kind: str,
    rows: Sequence[Mapping[str, Any]],
) -> bytes:
    """Gzip ADR series_seed_delta / series_repair_delta payload (canonical JSON)."""
    kind = str(object_kind).strip().lower()
    if kind not in {"series_seed_delta", "series_repair_delta"}:
        raise ValueError(f"unsupported delta object_kind: {object_kind!r}")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        code = str(row["instrument_code"])
        metric_key = str(row["metric_key"])
        flags = row.get("flags")
        if flags is None:
            flags_out: list[Any] = []
        elif isinstance(flags, list):
            flags_out = list(flags)
        else:
            flags_out = [flags]
        normalized.append(
            {
                "instrument_code": code,
                "metric_key": metric_key,
                "value": _json_number_or_null(row.get("value")),
                "flags": flags_out,
            }
        )
    normalized.sort(key=lambda item: (item["instrument_code"], item["metric_key"]))
    seen: set[tuple[str, str]] = set()
    for item in normalized:
        key = (item["instrument_code"], item["metric_key"])
        if key in seen:
            raise ValueError(f"duplicate delta row for {key!r}")
        seen.add(key)
    payload = {
        "schema_version": 1,
        "object_kind": kind,
        "request_id": str(request_id).strip(),
        "trade_date": str(trade_date).strip(),
        "metric_set_version_id": str(metric_set_version_id).strip().lower(),
        "generation_id": str(generation_id).strip().lower(),
        "rows": normalized,
    }
    return gzip_series_bytes(dump_canonical_json(payload))


def series_seed_delta_object_key(
    *,
    request_id: str,
    trade_date: str,
    generation_id: str,
    sha256: str,
    object_kind: str = "series_seed_delta",
) -> str:
    kind = str(object_kind).strip().lower()
    return (
        f"derived-inputs/monthly-new-core/{request_id.strip()}/delta/"
        f"kind={kind}/"
        f"trade-date={trade_date.strip()}/"
        f"generation={generation_id.strip().lower()}/"
        f"delta-sha256={sha256.strip().lower()}.json.gz"
    )


def load_existing_series_state(
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    metric_set_version_id: str,
    codes: Sequence[str],
    year: int,
) -> ExistingSeriesState:
    """Load committed year series for candidate codes (dates/series/flags/prior digests)."""
    state = ExistingSeriesState()
    code_set = {str(c).strip() for c in codes if str(c).strip()}
    if not code_set:
        return state
    set_id = metric_set_version_id.strip().lower()
    keys_by_code = generation_store.list_committed_series_keys(
        metric_set_version_id=set_id,
        series_year=int(year),
    )
    to_fetch: list[tuple[str, str]] = []
    for code in sorted(code_set):
        object_key = keys_by_code.get(code) or generation_store.get_committed_series_object_key(
            metric_set_version_id=set_id,
            instrument_code=code,
            series_year=int(year),
        )
        if object_key:
            to_fetch.append((code, object_key))
    if not to_fetch:
        return state

    def _load_one(code: str, object_key: str) -> tuple[str, bytes]:
        return code, r2_store.get_object(object_key)

    workers = max(1, min(_r2_concurrency(), len(to_fetch)))
    loaded: dict[str, bytes] = {}
    if workers == 1:
        for code, key in to_fetch:
            c, raw = _load_one(code, key)
            loaded[c] = raw
    else:
        # Parallel GET runs before any PUT; warm boto3 to avoid lazy-init races.
        warm = getattr(r2_store, "warm_client", None)
        if callable(warm):
            warm()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_load_one, code, key): code for code, key in to_fetch
            }
            for fut in as_completed(futures):
                code, raw = fut.result()
                loaded[code] = raw

    for code, raw in loaded.items():
        canonical = gunzip_series_bytes(raw)
        dates, series, flags = parse_series_canonical_bytes(canonical)
        state.dates_by_code[code] = list(dates)
        state.series_by_code[code] = {k: list(v) for k, v in series.items()}
        state.flags_by_code[code] = [dict(item) for item in flags]
        state.prior_digest_by_code[code] = compute_object_sha256(canonical)
    return state


def _join_series_logical_digest(digests: Sequence[str]) -> str:
    joined = "".join(sorted(d.strip().lower() for d in digests))
    return compute_object_sha256(joined.encode("utf-8"))


def _put_registered_object(
    *,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    generation_id: str,
    object_kind: str,
    object_key: str,
    logical_digest: str,
    content: bytes,
    content_type: str,
    trade_date: str | None = None,
    instrument_code: str | None = None,
    series_year: int | None = None,
) -> str:
    byte_sha = compute_object_sha256(content)
    size_bytes = len(content)
    rec = generation_store.register_pending_object(
        generation_id=generation_id,
        object_kind=object_kind,
        object_key=object_key,
        logical_digest=logical_digest,
        byte_sha256=byte_sha,
        size_bytes=size_bytes,
        trade_date=trade_date,
        instrument_code=instrument_code,
        series_year=series_year,
    )
    r2_store.put_create_only(object_key, content, content_type=content_type)
    generation_store.mark_object_uploaded(
        generation_id=generation_id,
        object_key=object_key,
        byte_sha256=byte_sha,
        size_bytes=size_bytes,
    )
    return rec.object_key


def _put_registered_objects_parallel(
    *,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    generation_id: str,
    items: Sequence[dict[str, Any]],
) -> list[str]:
    """Register serially, put in parallel, mark uploaded serially (code-safe)."""
    if not items:
        return []
    prepared: list[dict[str, Any]] = []
    for item in items:
        content = bytes(item["content"])
        object_key = str(item["object_key"])
        logical_digest = str(item["logical_digest"])
        byte_sha = compute_object_sha256(content)
        size_bytes = len(content)
        generation_store.register_pending_object(
            generation_id=generation_id,
            object_kind=str(item["object_kind"]),
            object_key=object_key,
            logical_digest=logical_digest,
            byte_sha256=byte_sha,
            size_bytes=size_bytes,
            trade_date=item.get("trade_date"),
            instrument_code=item.get("instrument_code"),
            series_year=item.get("series_year"),
        )
        prepared.append(
            {
                "object_key": object_key,
                "content": content,
                "content_type": str(item.get("content_type") or "application/octet-stream"),
                "byte_sha": byte_sha,
                "size_bytes": size_bytes,
            }
        )

    workers = max(1, min(_r2_concurrency(), len(prepared)))
    if workers == 1:
        for row in prepared:
            r2_store.put_create_only(
                row["object_key"],
                row["content"],
                content_type=row["content_type"],
            )
    else:
        warm = getattr(r2_store, "warm_client", None)
        if callable(warm):
            warm()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    r2_store.put_create_only,
                    row["object_key"],
                    row["content"],
                    content_type=row["content_type"],
                )
                for row in prepared
            ]
            for fut in as_completed(futures):
                fut.result()

    keys: list[str] = []
    for row in prepared:
        generation_store.mark_object_uploaded(
            generation_id=generation_id,
            object_key=row["object_key"],
            byte_sha256=row["byte_sha"],
            size_bytes=row["size_bytes"],
        )
        keys.append(row["object_key"])
    return keys


def run_series_only_trade_date(
    *,
    plan: SeriesOnlyWritePlan,
    metric_set_version_id: str,
    github_run_id: int,
    values_by_code: Mapping[str, Mapping[str, Any]],
    existing_state: ExistingSeriesState | None = None,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    metric_keys_ordered: Sequence[str] | None = None,
    set_fingerprint: str | None = None,
    repository: str = "local/stockradarsystem",
    writer_workflow: str = "monthly_new_core_backfill.yml",
) -> str | None:
    """Begin → put series+manifest+delta → commit for one trade_date.

    Returns generation_id, or None when expected_object_count==0 (progress-only).
    """
    if plan.expected_object_count == 0:
        return None

    if metric_keys_ordered is None or set_fingerprint is None:
        spec = load_metric_set_spec()
        keys = list(metric_keys_ordered) if metric_keys_ordered is not None else spec.metric_keys_ordered
        fingerprint = (
            set_fingerprint.strip().lower()
            if set_fingerprint is not None
            else spec.set_fingerprint
        )
    else:
        keys = list(metric_keys_ordered)
        fingerprint = set_fingerprint.strip().lower()
    metric_types = {key: "float" for key in keys}
    state = existing_state or ExistingSeriesState()
    year = int(str(plan.trade_date)[:4])
    prefixes = prefix_for(metric_set_version_id)

    begin_req = build_begin_request_for_plan(
        plan=plan,
        metric_set_version_id=metric_set_version_id,
        github_run_id=github_run_id,
        repository=repository,
        prior_absent_by_code=state.prior_absent_by_code(plan.write_codes),
        expected_prior_digest_by_code=state.prior_digest_by_code,
    )
    generation = generation_store.begin_generation(begin_req)
    generation_id = generation.generation_id

    object_keys: list[str] = []
    series_logical_digests: list[str] = []
    delta_rows: list[dict[str, Any]] = []
    pending_puts: list[dict[str, Any]] = []
    delta_kind = (
        "series_seed_delta" if plan.mode == "series_seed" else "series_repair_delta"
    )
    provenance = "series_seed" if plan.mode == "series_seed" else "series_repair"

    for code in plan.write_codes:
        raw_values = dict(values_by_code.get(code) or {})
        values = {key: _json_number_or_null(raw_values.get(key)) for key in keys}
        dates, series, flags, _wrote = merge_seed_observation(
            trade_date=plan.trade_date,
            metric_keys_ordered=keys,
            values=values,
            instrument_code=code,
            prior_dates=state.dates_by_code.get(code),
            prior_series=state.series_by_code.get(code),
            prior_flags=state.flags_by_code.get(code),
        )
        canonical = build_series_canonical_bytes(
            instrument_code=code,
            year=year,
            dates=dates,
            series=series,
            flags=flags,
            metric_keys_ordered=keys,
        )
        content = gzip_series_bytes(canonical)
        byte_sha = compute_object_sha256(content)
        logical = compute_object_sha256(canonical)
        series_logical_digests.append(logical)
        series_key = object_key_for(
            prefixes=prefixes,
            object_kind=DerivedArtifact.SERIES,
            instrument_code=code,
            year=year,
            generation_uuid=generation_id,
            object_sha256=byte_sha,
        )
        pending_puts.append(
            {
                "object_kind": "series",
                "object_key": series_key,
                "logical_digest": logical,
                "content": content,
                "content_type": SERIES_GZIP_CONTENT_TYPE,
                "instrument_code": code,
                "series_year": year,
            }
        )
        manifest_bytes = build_series_manifest_bytes(
            instrument_code=code,
            year=year,
            metric_set_version_id=metric_set_version_id,
            generation_id=generation_id,
            logical_digest=logical,
            object_sha256=byte_sha,
            object_size=len(content),
            writer_workflow=writer_workflow,
            set_fingerprint=fingerprint,
            source_github_run_id=github_run_id,
            row_count=len(dates),
            metric_keys_ordered=keys,
            mode=plan.mode,
            provenance=provenance,
            writer_version=DERIVED_WRITER_VERSION,
        )
        manifest_sha = compute_object_sha256(manifest_bytes)
        manifest_key = object_key_for(
            prefixes=prefixes,
            object_kind=DerivedArtifact.SERIES,
            instrument_code=code,
            year=year,
            generation_uuid=generation_id,
            object_sha256=manifest_sha,
            manifest=True,
        )
        pending_puts.append(
            {
                "object_kind": "series_manifest",
                "object_key": manifest_key,
                "logical_digest": logical,
                "content": manifest_bytes,
                "content_type": "application/json",
                "instrument_code": code,
                "series_year": year,
            }
        )
        row_flags = flags_for_values(
            instrument_code=code,
            metric_keys_ordered=keys,
            metric_types=metric_types,
            values_by_key=values,
        )
        for key in keys:
            delta_rows.append(
                {
                    "instrument_code": code,
                    "metric_key": key,
                    "value": values.get(key),
                    "flags": [],
                    "_row_flags": row_flags,
                }
            )

    object_keys.extend(
        _put_registered_objects_parallel(
            generation_store=generation_store,
            r2_store=r2_store,
            generation_id=generation_id,
            items=pending_puts,
        )
    )

    # Drop helper field; ADR rows keep flags as list.
    clean_delta_rows = [
        {
            "instrument_code": row["instrument_code"],
            "metric_key": row["metric_key"],
            "value": row["value"],
            "flags": row["flags"],
        }
        for row in delta_rows
    ]
    delta_bytes = build_series_seed_delta_bytes(
        request_id=plan.request_id,
        trade_date=plan.trade_date,
        metric_set_version_id=metric_set_version_id,
        generation_id=generation_id,
        object_kind=delta_kind,
        rows=clean_delta_rows,
    )
    delta_sha = compute_object_sha256(delta_bytes)
    delta_logical = compute_object_sha256(gunzip_series_bytes(delta_bytes))
    delta_key = series_seed_delta_object_key(
        request_id=plan.request_id,
        trade_date=plan.trade_date,
        generation_id=generation_id,
        sha256=delta_sha,
        object_kind=delta_kind,
    )
    object_keys.append(
        _put_registered_object(
            generation_store=generation_store,
            r2_store=r2_store,
            generation_id=generation_id,
            object_kind=delta_kind,
            object_key=delta_key,
            logical_digest=delta_logical,
            content=delta_bytes,
            content_type=SERIES_GZIP_CONTENT_TYPE,
            trade_date=plan.trade_date,
        )
    )

    object_set_digest = compute_object_set_digest(object_keys)
    generation_store.set_expected_object_set_digest(
        generation_id=generation_id,
        expected_object_set_digest=object_set_digest,
    )
    new_logical = _join_series_logical_digest(series_logical_digests)
    generation_store.commit_generation(
        generation_id=generation_id,
        new_logical_digest=new_logical,
        expected_old_digest=None,
    )
    return generation_id


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        ensure_seed_catalog_or_block()
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    existing = json.loads(args.existing_dates_json)
    plan = plan_series_only_trade_date(
        request_id=args.request_id,
        mode=args.mode,
        trade_date=args.trade_date,
        candidate_codes=json.loads(args.codes_json),
        existing_dates_by_code=existing,
    )
    if args.mode == "series_repair":
        validate_series_repair_approver(
            approver_github_login=args.approver_github_login or "",
            worker_github_actor=args.worker_github_actor
            or os.environ.get("GITHUB_ACTOR", ""),
        )
    payload = {
        "status": "ok",
        "request_id": plan.request_id,
        "mode": plan.mode,
        "trade_date": plan.trade_date,
        "write_codes": list(plan.write_codes),
        "resolved_noop_codes": list(plan.resolved_noop_codes),
        "expected_object_count": plan.expected_object_count,
        "artifact_profile": plan.artifact_profile,
        "generation_required": plan.expected_object_count > 0,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-005 series_only writer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan-trade-date")
    p.add_argument("--request-id", required=True)
    p.add_argument("--mode", default="series_seed", choices=["series_seed", "series_repair"])
    p.add_argument("--trade-date", required=True)
    p.add_argument("--codes-json", required=True)
    p.add_argument("--existing-dates-json", default="{}")
    p.add_argument("--approver-github-login", default="")
    p.add_argument("--worker-github-actor", default="")
    p.set_defaults(func=cmd_plan)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
