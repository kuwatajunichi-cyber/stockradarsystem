"""Cleanup old objects under runs/daily/ using LastModified (conservative path)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402


class RunsStagingDeleter(Protocol):
    def delete_objects(self, *, bucket: str, objects: list[dict[str, str]]) -> None: ...


def select_stale_object_keys(
    objects: list[dict[str, Any]],
    *,
    cutoff: datetime,
) -> list[dict[str, str]]:
    to_delete: list[dict[str, str]] = []
    for obj in objects:
        last_modified = obj.get("LastModified")
        if last_modified is None:
            continue
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        if last_modified < cutoff:
            to_delete.append({"Key": str(obj["Key"])})
    return to_delete


def batch_object_keys(keys: list[dict[str, str]], *, batch_size: int = 1000) -> list[list[dict[str, str]]]:
    return [keys[i : i + batch_size] for i in range(0, len(keys), batch_size)]


def cleanup_runs_staging_objects(
    *,
    objects: list[dict[str, Any]],
    cutoff: datetime,
    dry_run: bool,
    deleter: RunsStagingDeleter,
    bucket: str,
) -> int:
    to_delete = select_stale_object_keys(objects, cutoff=cutoff)
    if dry_run:
        return len(to_delete)
    deleted = 0
    for batch in batch_object_keys(to_delete):
        if not batch:
            continue
        deleter.delete_objects(bucket=bucket, objects=batch)
        deleted += len(batch)
    return deleted


def cleanup_runs_staging(*, keep_days: int, dry_run: bool = False) -> int:
    adapter = R2StagingAdapter()
    client = adapter._get_client()
    prefix = adapter._physical_key("runs/daily/")
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=adapter._bucket, Prefix=prefix):
        objects.extend(page.get("Contents") or [])

    class _Deleter:
        def delete_objects(self, *, bucket: str, objects: list[dict[str, str]]) -> None:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": objects, "Quiet": True},
            )

    deleted = cleanup_runs_staging_objects(
        objects=objects,
        cutoff=cutoff,
        dry_run=dry_run,
        deleter=_Deleter(),
        bucket=adapter._bucket,
    )
    if dry_run:
        print(f"dry-run: would delete {deleted} objects under {prefix}", file=sys.stderr)
        return 0
    print(f"deleted {deleted} objects under runs/daily/ older than {keep_days} days", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup R2 runs/daily staging objects")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(cleanup_runs_staging(keep_days=args.keep_days, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
