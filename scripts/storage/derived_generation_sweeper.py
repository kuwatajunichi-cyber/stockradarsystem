"""ADR-005 derived generation sweeper (tracked).

Deletes R2 under derived-snapshots/ and derived-series/ for orphan generations.
Never deletes derived-inputs/. Never deletes an object_key that still has a
committed derived_object_index row (protects series_seed_delta / series_repair_delta).
Does not purge superseded rows younger than retention (caller filters orphans only).
"""
from __future__ import annotations

import argparse
import json
import sys
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


def generation_sweep_prefixes(
    *,
    generation_id: str,
    metric_set_version_id: str,
    trade_date: str,
) -> list[str]:
    """Return R2 prefixes safe to delete for a failed/orphan generation."""
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
                "select": "id,object_key,generation_id,object_kind,instrument_code,trade_date,sha256",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep derived orphans (ADR-005 safe).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-summary", default=None)
    args = parser.parse_args(argv)

    # Contract comment retained for tests: do not delete derived-inputs
    assert "derived-inputs/" not in "".join(GENERATION_SWEEP_PREFIX_ROOTS)

    supabase = SupabaseRestAdapter.from_env()
    r2 = R2StagingAdapter()
    orphans = _list_unpurged_derived_orphans(supabase)
    committed_keys = _list_committed_object_keys(supabase)

    generation_ids = {str(row["generation_id"]) for row in orphans if row.get("generation_id")}
    generation_meta = _fetch_generation_meta(supabase, generation_ids)

    r2_deleted_keys: list[str] = []
    r2_prefix_deleted: dict[str, int] = {}
    purged_ids: list[str] = []
    skipped_protected: list[str] = []
    errors: list[str] = []

    for generation_id, meta in generation_meta.items():
        set_id = meta.get("metric_set_version_id", "")
        trade_date = meta.get("trade_date", "")
        if not set_id or not trade_date:
            continue
        for prefix in generation_sweep_prefixes(
            generation_id=generation_id,
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
            _mark_orphan_purged(supabase, object_id)
            purged_ids.append(object_id)
        except Exception as exc:
            errors.append(f"delete failed {object_key}: {exc}")

    summary = {
        "orphan_rows": len(orphans),
        "r2_object_keys_deleted": len(r2_deleted_keys),
        "r2_prefix_deleted": r2_prefix_deleted,
        "purged_object_ids": len(purged_ids),
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
