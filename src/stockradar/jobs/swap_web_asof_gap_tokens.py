"""Commit rewritten web-asof bundles for the pre-9.4 gap token mapping."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stockradar.jobs.write_web_asof_bundle import (
    WebAsofGenerationRequest,
    run_web_asof_generation,
)
from stockradar.storage.derived_generation import MetricGenerationPort
from stockradar.storage.r2_object_store import R2ObjectStorePort
from stockradar.storage.web_asof_bundle import gunzip_bundle_bytes
from stockradar.storage.web_asof_gap_token_swap import (
    SWAP_MODE,
    SWAP_REPOSITORY,
    SWAP_WORKFLOW,
    BundlePointer,
    GapSwapStats,
    swap_gap_bundle,
    swap_github_run_id,
)


@dataclass(frozen=True)
class SwapCommitResult:
    as_of: str
    status: str
    reason: str | None
    generation_id: str | None
    object_keys: tuple[str, ...]
    topix: GapSwapStats
    nikkei: GapSwapStats
    skipped: bool = False


def load_and_swap(
    r2_store: R2ObjectStorePort,
    pointer: BundlePointer,
) -> tuple[dict[str, Any], GapSwapStats]:
    blob = r2_store.get_object(pointer.object_key)
    payload = gunzip_bundle_bytes(blob)
    if str(payload.get("as_of")) != pointer.trade_date:
        raise ValueError(
            f"{pointer.object_key}: as_of {payload.get('as_of')!r} != {pointer.trade_date!r}"
        )
    if str(payload.get("benchmark") or "").strip().lower() != pointer.benchmark:
        raise ValueError(
            f"{pointer.object_key}: benchmark {payload.get('benchmark')!r} != {pointer.benchmark!r}"
        )
    return swap_gap_bundle(payload)


def commit_swapped_as_of(
    *,
    as_of: str,
    topix: BundlePointer,
    nikkei: BundlePointer,
    generation_store: MetricGenerationPort,
    r2_store: R2ObjectStorePort,
    existing_status: str | None = None,
) -> SwapCommitResult:
    """Rewrite one as-of. Skip committed identity. Do not retry failed identity."""
    if existing_status == "committed":
        return SwapCommitResult(
            as_of=as_of,
            status="skipped",
            reason="generation_already_committed",
            generation_id=None,
            object_keys=(),
            topix=GapSwapStats(0, 0, 0, 0, 0),
            nikkei=GapSwapStats(0, 0, 0, 0, 0),
            skipped=True,
        )
    if existing_status in {"failed", "pending"}:
        return SwapCommitResult(
            as_of=as_of,
            status="skipped",
            reason=f"identity_{existing_status}",
            generation_id=None,
            object_keys=(),
            topix=GapSwapStats(0, 0, 0, 0, 0),
            nikkei=GapSwapStats(0, 0, 0, 0, 0),
            skipped=True,
        )
    topix_payload, topix_stats = load_and_swap(r2_store, topix)
    nikkei_payload, nikkei_stats = load_and_swap(r2_store, nikkei)
    set_id = str(topix_payload["metric_set_version_id"])
    fingerprint = str(topix_payload["set_fingerprint"])
    result = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=as_of,
            metric_set_version_id=set_id,
            set_fingerprint=fingerprint,
            repository=SWAP_REPOSITORY,
            github_run_id=swap_github_run_id(as_of),
            payloads={"topix": topix_payload, "nikkei": nikkei_payload},
            workflow=SWAP_WORKFLOW,
            mode=SWAP_MODE,
            enforce_sma75=False,
        ),
        generation_store=generation_store,
        r2_store=r2_store,
    )
    return SwapCommitResult(
        as_of=as_of,
        status=result.status,
        reason=result.reason,
        generation_id=result.generation_id,
        object_keys=result.object_keys,
        topix=topix_stats,
        nikkei=nikkei_stats,
        skipped=result.skipped,
    )


def generation_result_as_dict(result: SwapCommitResult) -> dict[str, Any]:
    return {
        "as_of": result.as_of,
        "status": result.status,
        "reason": result.reason,
        "generation_id": result.generation_id,
        "object_keys": list(result.object_keys),
        "skipped": result.skipped,
        "topix": result.topix.__dict__,
        "nikkei": result.nikkei.__dict__,
    }


__all__ = [
    "SwapCommitResult",
    "commit_swapped_as_of",
    "generation_result_as_dict",
    "load_and_swap",
]
