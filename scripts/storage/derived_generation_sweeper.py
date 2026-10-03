"""ADR-005 derived generation sweeper (tracked).

Deletes R2 under derived-snapshots/ and derived-series/ for orphan generations.
Never deletes derived-inputs/. Never deletes an object_key that still has a
committed derived_object_index row (protects series_seed_delta / series_repair_delta).
Does not purge superseded rows younger than retention (caller filters orphans only).
Prefix-delete only orphan-only generations (no committed/superseded/pending objects,
and no latest_derived_observations rows). Mixed gens: per-key R2 + DB only.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseRestAdapter,
)
from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402

# Explicit contract: generation prefix deletes are only these two roots.
# Do not delete derived-inputs (seed/repair deltas live there as content-addressed).
GENERATION_SWEEP_PREFIX_ROOTS = ("derived-snapshots/", "derived-series/")
LIVE_NON_ORPHAN_STATUSES = frozenset({"committed", "superseded", "pending"})
DELETE_ORPHAN_BATCH_MAX = 20000
KIND_ORPHAN_ONLY = "orphan_only"
KIND_MIXED = "mixed"
KIND_BLOCKED_LATEST = "blocked_latest"
KIND_NO_ORPHAN = "no_orphan"


def generation_sweep_prefixes(
    *,
    generation_id: str,
    metric_set_version_id: str,
    trade_date: str,
) -> list[str]:
    """Return R2 prefixes safe to delete for a failed/orphan generation.

    Snapshot keys nest generation under trade-date. Series keys nest
    generation under symbol=/year=/, so the series prefix here is a
    no-op for the live layout; per-key delete from derived_object_index
    is the series path.
    """
    return [
        (
            f"derived-snapshots/metric-set={metric_set_version_id}/"
            f"trade-date={trade_date}/generation={generation_id}/"
        ),
        (
            f"derived-series/metric-set={metric_set_version_id}/"
            f"generation={generation_id}/"
        ),
    ]


def should_delete_orphan_object_key(
    *,
    object_key: str,
    object_kind: str | None,
    committed_object_keys: set[str],
) -> bool:
    """Protect committed rows (especially deltas under derived-inputs/)."""
    key = str(object_key or "").strip()
    if not key:
        return False
    if key.startswith("derived-inputs/"):
        return False
    if key in committed_object_keys:
        return False
    kind = str(object_kind or "")
    if kind in {"series_seed_delta", "series_repair_delta"} and key in committed_object_keys:
        return False
    return True


@dataclass(frozen=True)
class GenerationSweepPlan:
    generation_id: str
    kind: str
    prefix_delete: bool


def classify_generation_for_prefix_delete(
    *,
    statuses: set[str],
    latest_row_count: int = 0,
) -> str:
    """Classify a generation. Prefix-delete is allowed only for orphan_only."""
    normalized = {str(item).strip().lower() for item in statuses if str(item).strip()}
    has_orphan = "orphan" in normalized
    has_live = bool(normalized & LIVE_NON_ORPHAN_STATUSES)
    if int(latest_row_count or 0) > 0:
        return KIND_BLOCKED_LATEST
    if has_orphan and not has_live:
        return KIND_ORPHAN_ONLY
    if has_orphan and has_live:
        return KIND_MIXED
    return KIND_NO_ORPHAN


def should_prefix_delete_generation(kind: str) -> bool:
    return kind == KIND_ORPHAN_ONLY


def plan_generation_sweeps(
    *,
    statuses_by_generation: dict[str, set[str]],
    latest_counts: dict[str, int],
) -> list[GenerationSweepPlan]:
    plans: list[GenerationSweepPlan] = []
    for generation_id in sorted(statuses_by_generation):
        kind = classify_generation_for_prefix_delete(
            statuses=statuses_by_generation.get(generation_id) or set(),
            latest_row_count=int(latest_counts.get(generation_id) or 0),
        )
        plans.append(
            GenerationSweepPlan(
                generation_id=generation_id,
                kind=kind,
                prefix_delete=should_prefix_delete_generation(kind),
            )
        )
    return plans


def _list_unpurged_derived_orphans(supabase: Any) -> list[dict]:
    if isinstance(supabase, FakeSupabaseControlAdapter):
        return []
    rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        resp = supabase._request(
            "GET",
            "/rest/v1/derived_object_index",
            params={
                "status": "eq.orphan",
                "purged_at": "is.null",
                "select": "id,object_key,generation_id,object_kind,instrument_code,trade_date,byte_sha256",
                "order": "object_key",
                "limit": str(page_size),
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _list_committed_object_keys(supabase: Any) -> set[str]:
    if isinstance(supabase, FakeSupabaseControlAdapter):
        return set()
    keys: set[str] = set()
    offset = 0
    page_size = 1000
    while True:
        resp = supabase._request(
            "GET",
            "/rest/v1/derived_object_index",
            params={
                "status": "eq.committed",
                "select": "object_key",
                "limit": str(page_size),
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        for row in batch:
            k = str(row.get("object_key") or "").strip()
            if k:
                keys.add(k)
        if len(batch) < page_size:
            break
        offset += page_size
    return keys


def _mark_orphan_purged(supabase: Any, object_id: str) -> None:
    resp = supabase._request(
        "POST",
        "/rest/v1/rpc/mark_orphan_object_purged",
        json_body={"p_object_id": object_id},
    )
    resp.raise_for_status()


def _fetch_generation_meta(supabase: Any, generation_ids: set[str]) -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    for generation_id in sorted(generation_ids):
        resp = supabase._request(
            "GET",
            "/rest/v1/derived_generation_runs",
            params={
                "id": f"eq.{generation_id}",
                "select": "id,metric_set_version_id,trade_date,status",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list) and rows:
            row = rows[0]
            meta[generation_id] = {
                "metric_set_version_id": str(row.get("metric_set_version_id") or ""),
                "trade_date": str(row.get("trade_date") or ""),
                "status": str(row.get("status") or ""),
            }
    return meta


def _generation_has_non_orphan(supabase: Any, generation_id: str) -> bool:
    if isinstance(supabase, FakeSupabaseControlAdapter):
        return False
    resp = supabase._request(
        "GET",
        "/rest/v1/derived_object_index",
        params={
            "generation_id": f"eq.{generation_id}",
            "status": "in.(committed,superseded,pending)",
            "select": "id",
            "limit": "1",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    return isinstance(rows, list) and len(rows) > 0


def _generation_has_latest_observations(supabase: Any, generation_id: str) -> bool:
    if isinstance(supabase, FakeSupabaseControlAdapter):
        return False
    resp = supabase._request(
        "GET",
        "/rest/v1/latest_derived_observations",
        params={
            "generation_id": f"eq.{generation_id}",
            "select": "instrument_code",
            "limit": "1",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    return isinstance(rows, list) and len(rows) > 0


def _delete_orphan_rows_batch(supabase: Any, *, limit: int) -> int:
    resp = supabase._request(
        "POST",
        "/rest/v1/rpc/delete_orphan_derived_objects",
        json_body={"p_limit": int(limit)},
    )
    resp.raise_for_status()
    payload = resp.json()
    return int(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep derived orphans (ADR-005 safe).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-summary", default=None)
    parser.add_argument(
        "--delete-orphan-rows",
        action="store_true",
        help="Physically DELETE status=orphan rows via delete_orphan_derived_objects (migration 020).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DELETE_ORPHAN_BATCH_MAX,
        help=f"RPC batch size for --delete-orphan-rows (1..{DELETE_ORPHAN_BATCH_MAX}).",
    )
    args = parser.parse_args(argv)
    batch_size = max(1, min(int(args.batch_size), DELETE_ORPHAN_BATCH_MAX))

    # Contract comment retained for tests: do not delete derived-inputs
    assert "derived-inputs/" not in "".join(GENERATION_SWEEP_PREFIX_ROOTS)

    supabase = SupabaseRestAdapter.from_env()
    r2 = R2StagingAdapter()
    orphans = _list_unpurged_derived_orphans(supabase)
    committed_keys = _list_committed_object_keys(supabase)

    generation_ids = {str(row["generation_id"]) for row in orphans if row.get("generation_id")}
    generation_meta = _fetch_generation_meta(supabase, generation_ids)
    statuses_by_generation: dict[str, set[str]] = {
        gid: {"orphan"} for gid in generation_ids
    }
    latest_counts: dict[str, int] = {}
    for generation_id in sorted(generation_ids):
        if _generation_has_non_orphan(supabase, generation_id):
            statuses_by_generation[generation_id].update(LIVE_NON_ORPHAN_STATUSES)
        latest_counts[generation_id] = (
            1 if _generation_has_latest_observations(supabase, generation_id) else 0
        )
    plans = plan_generation_sweeps(
        statuses_by_generation=statuses_by_generation,
        latest_counts=latest_counts,
    )

    r2_deleted_keys: list[str] = []
    r2_prefix_deleted: dict[str, int] = {}
    prefix_skipped_mixed: list[str] = []
    prefix_skipped_latest: list[str] = []
    purged_ids: list[str] = []
    skipped_protected: list[str] = []
    errors: list[str] = []
    orphan_rows_deleted = 0

    for plan in plans:
        if plan.kind == KIND_MIXED:
            prefix_skipped_mixed.append(plan.generation_id)
            continue
        if plan.kind == KIND_BLOCKED_LATEST:
            prefix_skipped_latest.append(plan.generation_id)
            continue
        if not plan.prefix_delete:
            continue
        meta = generation_meta.get(plan.generation_id) or {}
        set_id = meta.get("metric_set_version_id", "")
        trade_date = meta.get("trade_date", "")
        if not set_id or not trade_date:
            errors.append(f"missing generation meta for prefix {plan.generation_id}")
            continue
        for prefix in generation_sweep_prefixes(
            generation_id=plan.generation_id,
            metric_set_version_id=set_id,
            trade_date=trade_date,
        ):
            if not any(prefix.startswith(root) for root in GENERATION_SWEEP_PREFIX_ROOTS):
                errors.append(f"refusing non-allowlisted prefix {prefix}")
                continue
            if args.dry_run:
                print(f"dry-run prefix delete: {prefix}")
                continue
            try:
                count = r2.delete_objects_with_prefix(prefix)
                if count:
                    r2_prefix_deleted[prefix] = count
            except Exception as exc:
                if "NoSuchKey" in str(exc):
                    continue
                errors.append(f"prefix delete failed {prefix}: {exc}")

    for row in orphans:
        object_id = str(row.get("id") or "")
        object_key = str(row.get("object_key") or "").strip()
        kind = str(row.get("object_kind") or "")
        if not should_delete_orphan_object_key(
            object_key=object_key,
            object_kind=kind,
            committed_object_keys=committed_keys,
        ):
            skipped_protected.append(object_key or object_id)
            continue
        if args.dry_run:
            print(f"dry-run delete r2: {object_key}")
            continue
        try:
            r2.delete_object(object_key)
            r2_deleted_keys.append(object_key)
        except Exception as exc:
            if "NoSuchKey" not in str(exc):
                errors.append(f"delete failed {object_key}: {exc}")
                continue
        if args.delete_orphan_rows:
            continue
        try:
            _mark_orphan_purged(supabase, object_id)
            purged_ids.append(object_id)
        except Exception as exc:
            errors.append(f"mark purged failed {object_id}: {exc}")

    if args.delete_orphan_rows:
        if args.dry_run:
            print(f"dry-run delete orphan rows batch_size={batch_size}")
        else:
            while True:
                try:
                    deleted = _delete_orphan_rows_batch(supabase, limit=batch_size)
                except Exception as exc:
                    errors.append(f"delete_orphan_derived_objects failed: {exc}")
                    break
                orphan_rows_deleted += deleted
                if deleted <= 0:
                    break

    summary = {
        "orphan_rows": len(orphans),
        "r2_object_keys_deleted": len(r2_deleted_keys),
        "r2_prefix_deleted": r2_prefix_deleted,
        "prefix_orphan_only": [
            item.generation_id for item in plans if item.prefix_delete
        ],
        "prefix_skipped_mixed": prefix_skipped_mixed,
        "prefix_skipped_latest": prefix_skipped_latest,
        "purged_object_ids": len(purged_ids),
        "orphan_rows_deleted": orphan_rows_deleted,
        "delete_orphan_rows": bool(args.delete_orphan_rows),
        "skipped_protected": len(skipped_protected),
        "errors": errors,
        "dry_run": args.dry_run,
        # not delete derived-inputs
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json_summary:
        Path(args.json_summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_summary).write_text(text + "\n", encoding="utf-8")
    return 1 if errors and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
