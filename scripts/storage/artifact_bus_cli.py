"""
Run artifact bus CLI: R2 staging put/get/record-fallback for daily.yml handoff.

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


def _is_r2_missing_exception(exc: BaseException | None) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        code = ""
        if isinstance(error, dict):
            code = str(error.get("Code") or "")
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code.lower() in {"nosuchkey", "notfound", "404"} or status == 404:
            return True
    return False


def _r2_failure_status(reason: str, exc: BaseException | None = None) -> str:
    if _is_r2_missing_exception(exc):
        return "r2_missing"
    lowered = reason.lower()
    if "nosuchkey" in lowered or "not found" in lowered or "404" in lowered:
        return "r2_missing"
    return "r2_error"


def _r2_get_failure_payload(
    *,
    entry_id: str,
    reason: str,
    phase: str,
    exc: BaseException | None = None,
) -> dict[str, object]:
    return {
        "status": _r2_failure_status(reason, exc),
        "entry_id": entry_id,
        "reason": reason,
        "handoff_source": None,
        "fallback_required": True,
        "fallback_used": False,
        "validated_count": 0,
        "degraded_reason": f"r2_{phase}_failed",
    }


def _r2_put_failure_payload(
    *, entry_id: str, reason: str, exc: BaseException | None = None
) -> dict[str, object]:
    return {
        "status": _r2_failure_status(reason, exc),
        "entry_id": entry_id,
        "reason": reason,
        "r2_put_ok": False,
        "github_upload_ok": None,
        "fallback_required": False,
        "validated_count": 0,
        "degraded_reason": "r2_put_failed",
    }


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
                    "r2_put_ok": False,
                    "validated_count": 0,
                    "degraded_reason": "optional_local_missing",
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
    try:
        adapter.put_object(blob_key, content, content_type=content_type)
        put_json(adapter, manifest_key, manifest)
    except Exception as exc:
        payload = _r2_put_failure_payload(
            entry_id=args.entry_id, reason=str(exc), exc=exc
        )
        _emit_result(payload, json_output=args.json_output)
        print(f"error: R2 put failed: {exc}", file=sys.stderr)
        return 1

    result_payload: dict[str, object] = {
        "status": "ok",
        "entry_id": args.entry_id,
        "logical_object_key": blob_key,
        "manifest_logical_key": manifest_key,
        "sha256": manifest["sha256"],
        "size_bytes": manifest["size_bytes"],
        "r2_put_ok": True,
        "validated_count": 1,
    }

    supabase_exit = _maybe_commit_artifact_index(
        args=args,
        blob_key=blob_key,
        manifest=manifest,
        content_type=content_type,
        entry=entry,
        result_payload=result_payload,
        json_output=args.json_output,
    )
    _emit_result(result_payload, json_output=args.json_output)
    if supabase_exit is not None:
        return supabase_exit

    return 0


def _maybe_commit_artifact_index(
    *,
    args: argparse.Namespace,
    blob_key: str,
    manifest: dict[str, object],
    content_type: str,
    entry: dict[str, object],
    result_payload: dict[str, object],
    json_output: str | None,
) -> int | None:
    import os

    from stockradar.storage.control_plane import normalize_rollout_stage, supabase_commit_is_fatal
    from stockradar.storage.mapping_catalog import load_mapping
    from stockradar.storage.supabase_client import (
        FakeSupabaseControlAdapter,
        SupabaseRestAdapter,
    )

    stage_raw = os.environ.get("PHASE3_ROLLOUT_STAGE", "").strip()
    if not stage_raw:
        mapping = load_mapping()
        stage_raw = str(mapping.get("phase3_rollout_stage") or "3a")
    stage = normalize_rollout_stage(stage_raw)
    fatal = supabase_commit_is_fatal(stage)

    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        adapter = FakeSupabaseControlAdapter()
    else:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            result_payload["supabase_commit_ok"] = False
            result_payload["supabase_commit_failed"] = "supabase_not_configured"
            return 1 if fatal else None
        adapter = SupabaseRestAdapter.from_env()

    workflow = str(entry.get("writer_workflow") or "daily.yml")
    run = adapter.get_run(workflow=workflow, github_run_id=int(args.run_id))
    if run is None and isinstance(adapter, FakeSupabaseControlAdapter):
        run = adapter.upsert_run(
            workflow=workflow,
            github_run_id=int(args.run_id),
            run_date=getattr(args, "run_date", None),
        )
    if run is None:
        result_payload["supabase_commit_ok"] = False
        result_payload["supabase_commit_failed"] = "runs_row_missing"
        return 1 if fatal else None

    retention = str(entry.get("retention_policy") or "")
    pending_id: str | None = None
    try:
        pending = adapter.insert_artifact_index_pending(
            run_id=str(run["id"]),
            source_name=args.source_name,
            object_key=blob_key,
            sha256=str(manifest["sha256"]),
            size_bytes=int(manifest["size_bytes"]),
            content_type=content_type,
            retention_policy=retention or None,
        )
        pending_id = str(pending["id"])
        committed = adapter.commit_artifact_index(artifact_id=pending_id)
        result_payload["supabase_commit_ok"] = True
        result_payload["artifact_index_id"] = committed["id"]
        result_payload["artifact_index_status"] = committed["status"]
        return None
    except Exception as exc:
        if pending_id:
            try:
                adapter.mark_artifact_index_orphan(artifact_id=pending_id)
            except Exception:
                pass
        result_payload["supabase_commit_ok"] = False
        result_payload["supabase_commit_failed"] = str(exc)
        print(f"error: artifact_index commit failed: {exc}", file=sys.stderr)
        return 1 if fatal else None


def _optional_get_missing_payload(*, entry_id: str, reason: str, phase: str) -> dict[str, object]:
    return {
        "status": "skipped_optional_missing",
        "entry_id": entry_id,
        "reason": reason,
        "handoff_source": None,
        "fallback_required": False,
        "fallback_used": False,
        "validated_count": 0,
        "degraded_reason": f"optional_r2_{phase}_missing",
    }


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
        if optional and _r2_failure_status(str(exc), exc) == "r2_missing":
            payload = _optional_get_missing_payload(
                entry_id=args.entry_id, reason=str(exc), phase="manifest"
            )
            _emit_result(payload, json_output=args.json_output)
            return 0
        payload = _r2_get_failure_payload(
            entry_id=args.entry_id, reason=str(exc), phase="manifest", exc=exc
        )
        _emit_result(payload, json_output=args.json_output)
        print(f"error: manifest get failed: {exc}", file=sys.stderr)
        return 1

    try:
        content = adapter.get_object(blob_key)
    except Exception as exc:
        if optional and _r2_failure_status(str(exc), exc) == "r2_missing":
            payload = _optional_get_missing_payload(
                entry_id=args.entry_id, reason=str(exc), phase="blob"
            )
            _emit_result(payload, json_output=args.json_output)
            return 0
        payload = _r2_get_failure_payload(
            entry_id=args.entry_id, reason=str(exc), phase="blob", exc=exc
        )
        _emit_result(payload, json_output=args.json_output)
        print(f"error: blob get failed: {exc}", file=sys.stderr)
        return 1

    sha = _sha256_bytes(content)
    ok, msg = verify_run_artifact_manifest(
        manifest, content_sha256=sha, size_bytes=len(content)
    )
    if not ok:
        payload = {
            "status": "mismatch",
            "entry_id": args.entry_id,
            "message": msg,
            "handoff_source": None,
            "fallback_required": not optional,
            "fallback_used": False,
            "validated_count": 0,
            "degraded_reason": "r2_manifest_mismatch",
        }
        _emit_result(payload, json_output=args.json_output)
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
            "handoff_source": "r2",
            "fallback_required": False,
            "fallback_used": False,
            "validated_count": 1,
        },
        json_output=args.json_output,
    )
    return 0


def cmd_record_fallback(args: argparse.Namespace) -> int:
    """Record successful GitHub artifact fallback after download-artifact."""
    local_path = Path(args.local_path)
    optional = args.optional if args.optional is not None else entry_is_optional(args.entry_id)
    if not local_path.is_file():
        if optional:
            _emit_result(
                {
                    "status": "skipped_optional_missing",
                    "entry_id": args.entry_id,
                    "local_path": str(local_path),
                    "handoff_source": None,
                    "fallback_required": False,
                    "fallback_used": True,
                    "validated_count": 0,
                    "degraded_reason": "optional_github_fallback_missing",
                },
                json_output=args.json_output,
            )
            return 0
        payload = {
            "status": "handoff_failed",
            "entry_id": args.entry_id,
            "local_path": str(local_path),
            "handoff_source": None,
            "fallback_required": False,
            "fallback_used": True,
            "validated_count": 0,
            "degraded_reason": "github_fallback_missing",
        }
        _emit_result(payload, json_output=args.json_output)
        print(f"error: required github fallback file missing: {local_path}", file=sys.stderr)
        return 1

    sha = compute_sha256(local_path)
    _emit_result(
        {
            "status": "ok",
            "entry_id": args.entry_id,
            "local_path": str(local_path),
            "sha256": sha,
            "size_bytes": local_path.stat().st_size,
            "handoff_source": "github_fallback",
            "fallback_required": False,
            "fallback_used": True,
            "validated_count": 1,
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

    fb_p = sub.add_parser("record-fallback")
    add_common(fb_p)
    fb_p.add_argument("--local-path", required=True)
    fb_p.set_defaults(func=cmd_record_fallback)

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
