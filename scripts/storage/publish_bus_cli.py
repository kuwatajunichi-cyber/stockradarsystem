"""Daily publish bus CLI: R2 published/ namespace + Supabase publish_status."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.daily_publish_manifest import (  # noqa: E402
    build_daily_publish_manifest,
    resolve_publish_manifest_object_key,
    resolve_publish_object_key,
    serialize_daily_publish_manifest,
)
from stockradar.storage.mapping_catalog import load_mapping  # noqa: E402
from stockradar.storage.phase4_rollout import (  # noqa: E402
    publish_commit_is_fatal,
    publish_dual_write_enabled,
    resolve_phase4_rollout_stage,
)
from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseControlPort,
    SupabaseRestAdapter,
)
from stockradar.utils.manifest import compute_sha256  # noqa: E402
from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402


def _adapter_supabase() -> SupabaseControlPort | None:
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        return None
    return SupabaseRestAdapter.from_env()


def _r2() -> R2StagingAdapter:
    return R2StagingAdapter()


def _emit(payload: dict[str, object], json_output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output:
        Path(json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(json_output).write_text(text + "\n", encoding="utf-8")


def _stage(args: argparse.Namespace) -> str:
    return resolve_phase4_rollout_stage(
        cli_override=getattr(args, "phase4_rollout_stage", None),
        mapping=load_mapping(),
    )


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return "text/csv"
    if path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def cmd_commit(args: argparse.Namespace) -> int:
    stage = _stage(args)
    if not publish_dual_write_enabled(stage):
        _emit({"status": "skipped", "reason": "publish_dual_write_disabled"}, args.json_output)
        return 0

    fatal = publish_commit_is_fatal(stage)
    local_path = Path(args.local_path)
    if not local_path.is_file():
        print(f"error: missing local file: {local_path}", file=sys.stderr)
        return 1 if fatal else 0

    supabase = _adapter_supabase()
    if supabase is None:
        _emit({"status": "error", "supabase_commit_ok": False, "reason": "supabase_not_configured"}, args.json_output)
        return 1 if fatal else 0

    run = supabase.get_run(workflow=args.workflow, github_run_id=int(args.github_run_id))
    if run is None:
        msg = f"runs row missing for {args.workflow} {args.github_run_id}"
        _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": msg}, args.json_output)
        return 1 if fatal else 0

    blob_bytes = local_path.read_bytes()
    sha256 = compute_sha256(str(local_path))
    size_bytes = len(blob_bytes)
    content_type = args.content_type or _content_type(local_path)
    object_key = resolve_publish_object_key(
        run_date=args.run_date,
        visibility=args.visibility,
        filename=args.filename,
    )
    manifest_key = resolve_publish_manifest_object_key(
        run_date=args.run_date,
        visibility=args.visibility,
        logical_kind=args.logical_kind,
    )

    publish_id: str | None = None
    try:
        pending = supabase.insert_publish_status_pending(
            run_id=str(run["id"]),
            workflow=args.workflow,
            github_run_id=int(args.github_run_id),
            run_date=args.run_date,
            logical_kind=args.logical_kind,
            visibility=args.visibility,
            object_key=object_key,
            manifest_object_key=manifest_key,
            size_bytes=size_bytes,
            sha256=sha256,
            content_type=content_type,
        )
        publish_id = str(pending["id"])
        if pending.get("status") == "committed":
            same_publish = (
                str(pending.get("sha256")) == sha256
                and int(pending.get("size_bytes")) == size_bytes
                and str(pending.get("object_key")) == object_key
            )
            if same_publish:
                try:
                    committed_manifest = build_daily_publish_manifest(
                        run_id=str(args.github_run_id),
                        workflow=args.workflow,
                        github_run_id=int(args.github_run_id),
                        run_date=args.run_date,
                        logical_kind=args.logical_kind,
                        visibility=args.visibility,
                        object_key=object_key,
                        size_bytes=size_bytes,
                        sha256=sha256,
                        content_type=content_type,
                        publish_id=publish_id,
                        publish_status="committed",
                    )
                    _r2().put_object(
                        manifest_key,
                        serialize_daily_publish_manifest(committed_manifest),
                        content_type="application/json",
                    )
                except Exception as exc:
                    print(f"warning: idempotent manifest reconcile failed: {exc}", file=sys.stderr)
                _emit(
                    {
                        "status": "ok",
                        "supabase_commit_ok": True,
                        "publish_id": publish_id,
                        "object_key": object_key,
                        "manifest_object_key": manifest_key,
                        "degraded_reason": None,
                        "idempotent": True,
                    },
                    args.json_output,
                )
                return 0
            _emit(
                {
                    "status": "error",
                    "error": "publish_mismatch",
                    "supabase_commit_ok": False,
                    "publish_id": publish_id,
                    "object_key": object_key,
                    "expected_sha256": sha256,
                    "committed_sha256": pending.get("sha256"),
                },
                args.json_output,
            )
            return 2
    except Exception as exc:
        _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)}, args.json_output)
        return 1 if fatal else 0

    degraded_reason: str | None = None
    try:
        _r2().put_object(object_key, blob_bytes, content_type=content_type)
        pending_manifest = build_daily_publish_manifest(
            run_id=str(args.github_run_id),
            workflow=args.workflow,
            github_run_id=int(args.github_run_id),
            run_date=args.run_date,
            logical_kind=args.logical_kind,
            visibility=args.visibility,
            object_key=object_key,
            size_bytes=size_bytes,
            sha256=sha256,
            content_type=content_type,
            publish_id=publish_id,
            publish_status="pending",
        )
        _r2().put_object(
            manifest_key,
            serialize_daily_publish_manifest(pending_manifest),
            content_type="application/json",
        )
    except Exception as exc:
        if publish_id:
            try:
                supabase.mark_publish_status_orphan(publish_id=publish_id)
            except Exception:
                pass
        print(f"error: R2 publish put failed: {exc}", file=sys.stderr)
        return 1 if fatal else 0

    try:
        committed = supabase.commit_publish_status(publish_id=publish_id or "")
    except Exception as exc:
        if publish_id:
            try:
                supabase.mark_publish_status_orphan(publish_id=publish_id)
            except Exception:
                pass
        _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)}, args.json_output)
        return 1 if fatal else 0

    try:
        committed_manifest = build_daily_publish_manifest(
            run_id=str(args.github_run_id),
            workflow=args.workflow,
            github_run_id=int(args.github_run_id),
            run_date=args.run_date,
            logical_kind=args.logical_kind,
            visibility=args.visibility,
            object_key=object_key,
            size_bytes=size_bytes,
            sha256=sha256,
            content_type=content_type,
            publish_id=publish_id,
            publish_status="committed",
        )
        _r2().put_object(
            manifest_key,
            serialize_daily_publish_manifest(committed_manifest),
            content_type="application/json",
        )
    except Exception as exc:
        degraded_reason = "manifest_reconcile_pending"
        print(f"warning: committed manifest re-put failed: {exc}", file=sys.stderr)

    _emit(
        {
            "status": "ok",
            "supabase_commit_ok": True,
            "publish_id": committed["id"],
            "object_key": object_key,
            "manifest_object_key": manifest_key,
            "degraded_reason": degraded_reason,
        },
        args.json_output,
    )
    return 0


def cmd_reconcile_manifest(args: argparse.Namespace) -> int:
    supabase = _adapter_supabase()
    if supabase is None:
        print("error: supabase not configured", file=sys.stderr)
        return 1

    row = supabase.get_publish_status(publish_id=args.publish_id)
    if row is None:
        print(f"error: publish_status row not found: {args.publish_id}", file=sys.stderr)
        return 1
    if row.get("status") != "committed":
        print(f"error: publish_status not committed: {row.get('status')}", file=sys.stderr)
        return 1

    manifest = build_daily_publish_manifest(
        run_id=str(row["run_id"]),
        workflow=str(row["workflow"]),
        github_run_id=int(row["github_run_id"]),
        run_date=str(row["run_date"]),
        logical_kind=str(row["logical_kind"]),
        visibility=str(row["visibility"]),
        object_key=str(row["object_key"]),
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]),
        content_type=str(row["content_type"]),
        publish_id=str(row["id"]),
        publish_status="committed",
    )
    manifest_key = str(row["manifest_object_key"])
    _r2().put_object(
        manifest_key,
        serialize_daily_publish_manifest(manifest),
        content_type="application/json",
    )
    _emit({"status": "ok", "manifest_object_key": manifest_key}, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Daily publish bus CLI (Phase 4).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--phase4-rollout-stage", default=None)
    common.add_argument("--json-output", default=None)

    p_commit = sub.add_parser("commit", parents=[common])
    p_commit.add_argument("--workflow", default="daily.yml")
    p_commit.add_argument("--github-run-id", required=True)
    p_commit.add_argument("--run-date", required=True)
    p_commit.add_argument("--logical-kind", required=True, choices=("indicators_csv", "indicators_xlsx"))
    p_commit.add_argument("--visibility", required=True, choices=("work", "paid"))
    p_commit.add_argument("--local-path", required=True)
    p_commit.add_argument("--filename", required=True)
    p_commit.add_argument("--content-type", default=None)

    p_rec = sub.add_parser("reconcile-manifest", parents=[common])
    p_rec.add_argument("--publish-id", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "commit":
        sys.exit(cmd_commit(args))
    if args.cmd == "reconcile-manifest":
        sys.exit(cmd_reconcile_manifest(args))
    parser.error("unknown command")


if __name__ == "__main__":
    main()
