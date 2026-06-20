"""
Run artifact bus CLI: R2 staging put/get/shadow-validate for daily.yml handoff.

Usage (producer):
  python scripts/storage/artifact_bus_cli.py put \\
    --entry-id artifact-daily-core-csv \\
    --run-id "$GITHUB_RUN_ID" \\
    --run-date "$RUN_DATE" \\
    --source-name "daily-core-csv-$GITHUB_RUN_ID" \\
    --local-path data/universe/jpx/core_selected_staging/equity_domestic_core_with_name.csv \\
    --content-type text/csv

Usage (consumer):
  python scripts/storage/artifact_bus_cli.py get \\
    --entry-id artifact-daily-core-csv \\
    --run-id "$GITHUB_RUN_ID" \\
    --run-date "$RUN_DATE" \\
    --local-path data/universe/jpx/core_selected_staging/equity_domestic_core_with_name.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.artifact_bus import (  # noqa: E402
    create_run_artifact_manifest,
    entry_is_optional,
    manifest_logical_key,
    resolve_entry_logical_key,
    verify_run_artifact_manifest,
)
from stockradar.storage.mapping_catalog import get_entry  # noqa: E402
from stockradar.utils.manifest import compute_sha256  # noqa: E402
from scripts.storage.r2_staging_client import (  # noqa: E402
    R2StagingAdapter,
    get_json,
    put_json,
)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".json":
        return "application/json"
    if suffix == ".zip":
        return "application/zip"
    if suffix in {".xlsx"}:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def _adapter_from_env() -> R2StagingAdapter:
    return R2StagingAdapter()


def _emit_result(payload: dict[str, object], *, json_output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output:
        out_path = Path(json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")


def cmd_put(args: argparse.Namespace) -> int:
    local_path = Path(args.local_path)
    if not local_path.is_file():
        optional = args.optional if args.optional is not None else entry_is_optional(args.entry_id)
        if optional:
            _emit_result(
                {
                    "status": "skipped_optional_missing",
                    "entry_id": args.entry_id,
                    "local_path": str(local_path),
                    "validated_count": 0,
                },
                json_output=args.json_output,
            )
            return 0
        print(f"error: required local file missing: {local_path}", file=sys.stderr)
        return 1

    blob_key = resolve_entry_logical_key(
        args.entry_id, run_id=args.run_id, run_date=args.run_date
    )
    manifest_key = manifest_logical_key(args.entry_id, args.run_id)
    optional = args.optional if args.optional is not None else entry_is_optional(args.entry_id)
    content_type = args.content_type or _guess_content_type(local_path)
    entry = get_entry(args.entry_id)
    workflow = str(entry.get("writer_workflow") or "daily.yml")

    manifest = create_run_artifact_manifest(
        entry_id=args.entry_id,
        source_name=args.source_name,
        logical_object_key=blob_key,
        local_path=str(local_path),
        content_type=content_type,
        optional=optional,
        github_run_id=args.run_id,
        run_date=args.run_date,
        workflow=workflow,
    )

    adapter = _adapter_from_env()
    content = local_path.read_bytes()
    adapter.put_object(blob_key, content, content_type=content_type)
    put_json(adapter, manifest_key, manifest)

    _emit_result(
        {
            "status": "ok",
            "entry_id": args.entry_id,
            "logical_object_key": blob_key,
            "manifest_logical_key": manifest_key,
            "sha256": manifest["sha256"],
            "size_bytes": manifest["size_bytes"],
        },
        json_output=args.json_output,
    )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    local_path = Path(args.local_path)
    optional = args.optional if args.optional is not None else entry_is_optional(args.entry_id)
    blob_key = resolve_entry_logical_key(
        args.entry_id, run_id=args.run_id, run_date=args.run_date
    )
    manifest_key = manifest_logical_key(args.entry_id, args.run_id)
    adapter = _adapter_from_env()

    try:
        manifest = get_json(adapter, manifest_key)
    except Exception as exc:
        if optional:
            _emit_result(
                {
                    "status": "skipped_optional_missing",
                    "entry_id": args.entry_id,
                    "reason": str(exc),
                    "validated_count": 0,
                },
                json_output=args.json_output,
            )
            return 0
        print(f"error: manifest get failed: {exc}", file=sys.stderr)
        return 1

    try:
        content = adapter.get_object(blob_key)
    except Exception as exc:
        if optional:
            _emit_result(
                {
                    "status": "skipped_optional_missing",
                    "entry_id": args.entry_id,
                    "reason": str(exc),
                    "validated_count": 0,
                },
                json_output=args.json_output,
            )
            return 0
        print(f"error: blob get failed: {exc}", file=sys.stderr)
        return 1

    sha = _sha256_bytes(content)
    ok, msg = verify_run_artifact_manifest(
        manifest, content_sha256=sha, size_bytes=len(content)
    )
    if not ok:
        print(f"error: manifest verify failed: {msg}", file=sys.stderr)
        return 1

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    _emit_result(
        {
            "status": "ok",
            "entry_id": args.entry_id,
            "logical_object_key": blob_key,
            "manifest_logical_key": manifest_key,
            "local_path": str(local_path),
            "sha256": sha,
            "size_bytes": len(content),
        },
        json_output=args.json_output,
    )
    return 0


def cmd_shadow_validate(args: argparse.Namespace) -> int:
    """Compare local file (GitHub artifact path) with R2 staging blob via manifest."""
    local_path = Path(args.local_path)
    optional = args.optional if args.optional is not None else entry_is_optional(args.entry_id)
    if not local_path.is_file():
        if optional:
            _emit_result(
                {
                    "status": "skipped_optional_missing",
                    "entry_id": args.entry_id,
                    "local_path": str(local_path),
                    "validated_count": 0,
                    "degraded_reason": "optional_local_missing",
                },
                json_output=args.json_output,
            )
            return 0
        print(f"error: local file missing for shadow validate: {local_path}", file=sys.stderr)
        return 1

    blob_key = resolve_entry_logical_key(
        args.entry_id, run_id=args.run_id, run_date=args.run_date
    )
    manifest_key = manifest_logical_key(args.entry_id, args.run_id)
    adapter = _adapter_from_env()
    try:
        manifest = get_json(adapter, manifest_key)
        content = adapter.get_object(blob_key)
    except Exception as exc:
        print(f"error: R2 shadow validate failed: {exc}", file=sys.stderr)
        return 1
    local_sha = compute_sha256(local_path)
    remote_sha = _sha256_bytes(content)
    ok, msg = verify_run_artifact_manifest(
        manifest, content_sha256=remote_sha, size_bytes=len(content)
    )
    if not ok or local_sha != remote_sha:
        mismatch = {
            "status": "mismatch",
            "entry_id": args.entry_id,
            "local_sha256": local_sha,
            "remote_sha256": remote_sha,
            "message": msg or "sha256 mismatch",
            "validated_count": 0,
        }
        if args.json_output:
            out_path = Path(args.json_output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(mismatch, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(mismatch, ensure_ascii=False), file=sys.stderr)
        return 1

    _emit_result(
        {
            "status": "ok",
            "entry_id": args.entry_id,
            "validated_count": 1,
            "logical_object_key": blob_key,
            "manifest_logical_key": manifest_key,
            "sha256": local_sha,
            "size_bytes": local_path.stat().st_size,
        },
        json_output=args.json_output,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run artifact bus R2 staging CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--entry-id", required=True)
        p.add_argument("--run-id", required=True)
        p.add_argument("--run-date", required=True)
        p.add_argument("--optional", choices=("true", "false"), default=None)
        p.add_argument(
            "--json-output",
            default=None,
            help="Write the same JSON payload as stdout to this path",
        )

    put_p = sub.add_parser("put")
    add_common(put_p)
    put_p.add_argument("--source-name", required=True)
    put_p.add_argument("--local-path", required=True)
    put_p.add_argument("--content-type", default=None)
    put_p.set_defaults(func=cmd_put)

    get_p = sub.add_parser("get")
    add_common(get_p)
    get_p.add_argument("--local-path", required=True)
    get_p.set_defaults(func=cmd_get)

    val_p = sub.add_parser("shadow-validate")
    add_common(val_p)
    val_p.add_argument("--local-path", required=True)
    val_p.set_defaults(func=cmd_shadow_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.optional is not None:
        args.optional = args.optional == "true"
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
