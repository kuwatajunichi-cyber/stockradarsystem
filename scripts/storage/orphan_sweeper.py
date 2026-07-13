"""Orphan sweeper: R2 blobs + Supabase orphan rows (Phase 3)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.supabase_client import SupabaseRestAdapter  # noqa: E402
from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402


def _object_keys_from_row(row: dict) -> list[str]:
    table = row.get("_table")
    if table == "artifact_index":
        key = row.get("object_key")
        return [str(key)] if key else []
    if table == "cache_index":
        if row.get("object_key"):
            return [str(row["object_key"])]
        obj = row.get("object_keys")
        if isinstance(obj, dict):
            keys: list[str] = []
            for part in ("csv", "manifest"):
                spec = obj.get(part)
                if isinstance(spec, dict) and spec.get("object_key"):
                    keys.append(str(spec["object_key"]))
            return keys
    if table == "monthly_snapshots":
        obj = row.get("object_keys")
        if isinstance(obj, dict):
            keys: list[str] = []
            for part in ("ipo", "illiquid", "core", "manifest"):
                spec = obj.get(part)
                if isinstance(spec, dict) and spec.get("object_key"):
                    keys.append(str(spec["object_key"]))
            return keys
    if table == "publish_status":
        keys: list[str] = []
        if row.get("object_key"):
            keys.append(str(row["object_key"]))
        if row.get("manifest_object_key"):
            keys.append(str(row["manifest_object_key"]))
        return keys
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep orphan R2 objects and Supabase rows.")
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    supabase = SupabaseRestAdapter.from_env()
    r2 = R2StagingAdapter()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.keep_days)
    orphans = supabase.list_orphan_rows()
    deleted = 0
    for row in orphans:
        created = row.get("created_at_utc") or row.get("committed_at_utc")
        if created:
            try:
                ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                if ts > cutoff:
                    continue
            except ValueError:
                pass
        for key in _object_keys_from_row(row):
            if args.dry_run:
                print(f"dry-run delete r2: {key}")
            else:
                try:
                    r2.delete_object(key)
                except Exception as exc:
                    print(f"warning: r2 delete failed {key}: {exc}", file=sys.stderr)
                    continue
        if not args.dry_run:
            supabase.delete_row(table=str(row["_table"]), row_id=str(row["id"]))
        deleted += 1
    print(f"orphan_rows_processed={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
