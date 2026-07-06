"""CLI for Supabase control plane (runs, artifact_index)."""
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

from stockradar.storage.control_plane import normalize_rollout_stage, supabase_commit_is_fatal  # noqa: E402
from stockradar.storage.mapping_catalog import get_entry, load_mapping  # noqa: E402
from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseControlPort,
    SupabaseRestAdapter,
)


def _adapter_from_env() -> SupabaseControlPort | None:
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        return None
    return SupabaseRestAdapter.from_env()


def _emit(payload: dict[str, object], json_output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output:
        Path(json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(json_output).write_text(text + "\n", encoding="utf-8")


def _rollout_stage(args: argparse.Namespace) -> str:
    if args.phase3_rollout_stage:
        return normalize_rollout_stage(args.phase3_rollout_stage)
    env = os.environ.get("PHASE3_ROLLOUT_STAGE", "").strip()
    if env:
        return normalize_rollout_stage(env)
    mapping = load_mapping()
    return normalize_rollout_stage(str(mapping.get("phase3_rollout_stage") or "3a"))


def cmd_upsert_run(args: argparse.Namespace) -> int:
    adapter = _adapter_from_env()
    if adapter is None:
        print("error: Supabase not configured", file=sys.stderr)
        return 1
    row = adapter.upsert_run(
        workflow=args.workflow,
        github_run_id=int(args.github_run_id),
        run_date=args.run_date or None,
        status=args.status,
    )
    _emit({"status": "ok", "run_id": row["id"], "workflow": args.workflow}, args.json_output)
    return 0


def cmd_commit_artifact(args: argparse.Namespace) -> int:
    adapter = _adapter_from_env()
    stage = _rollout_stage(args)
    fatal = supabase_commit_is_fatal(stage)

    if adapter is None:
        payload = {
            "status": "skipped",
            "supabase_commit_ok": False,
            "supabase_commit_failed": "supabase_not_configured",
        }
        _emit(payload, args.json_output)
        return 1 if fatal else 0

    run = adapter.get_run(workflow=args.workflow, github_run_id=int(args.github_run_id))
    if run is None:
        msg = f"runs row missing for {args.workflow} run {args.github_run_id}"
        _emit(
            {
                "status": "error",
                "supabase_commit_ok": False,
                "supabase_commit_failed": msg,
            },
            args.json_output,
        )
        return 1 if fatal else 0

    entry = get_entry(args.entry_id)
    retention = str(entry.get("retention_policy") or "")

    try:
        pending = adapter.insert_artifact_index_pending(
            run_id=str(run["id"]),
            source_name=args.source_name,
            object_key=args.object_key,
            sha256=args.sha256,
            size_bytes=int(args.size_bytes),
            content_type=args.content_type,
            retention_policy=retention or None,
        )
        committed = adapter.commit_artifact_index(artifact_id=str(pending["id"]))
        _emit(
            {
                "status": "ok",
                "supabase_commit_ok": True,
                "artifact_index_id": committed["id"],
                "artifact_index_status": committed["status"],
            },
            args.json_output,
        )
        return 0
    except Exception as exc:
        aid = locals().get("pending", {}).get("id") if "pending" in locals() else None
        if aid:
            try:
                adapter.mark_artifact_index_orphan(artifact_id=str(aid))
            except Exception:
                pass
        _emit(
            {
                "status": "error",
                "supabase_commit_ok": False,
                "supabase_commit_failed": str(exc),
            },
            args.json_output,
        )
        print(f"error: artifact_index commit failed: {exc}", file=sys.stderr)
        return 1 if fatal else 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Supabase control plane CLI (Phase 3).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("upsert-run")
    p_run.add_argument("--workflow", required=True)
    p_run.add_argument("--github-run-id", required=True)
    p_run.add_argument("--run-date", default="")
    p_run.add_argument("--status", default="running")
    p_run.add_argument("--json-output", default=None)

    p_art = sub.add_parser("commit-artifact")
    p_art.add_argument("--entry-id", required=True)
    p_art.add_argument("--workflow", default="daily.yml")
    p_art.add_argument("--github-run-id", required=True)
    p_art.add_argument("--source-name", required=True)
    p_art.add_argument("--object-key", required=True)
    p_art.add_argument("--sha256", required=True)
    p_art.add_argument("--size-bytes", required=True)
    p_art.add_argument("--content-type", default="application/octet-stream")
    p_art.add_argument("--phase3-rollout-stage", default=None)
    p_art.add_argument("--json-output", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "upsert-run":
        sys.exit(cmd_upsert_run(args))
    if args.cmd == "commit-artifact":
        sys.exit(cmd_commit_artifact(args))
    parser.error("unknown command")


if __name__ == "__main__":
    main()
