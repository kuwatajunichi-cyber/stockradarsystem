"""Warm cache bus CLI: R2 cache/ namespace + Supabase cache_index / cache_pointers."""
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

from stockradar.jobs.cache_ops import should_rotate_cache  # noqa: E402
from stockradar.jobs.patch_universe_daily import MANIFEST_FILENAME  # noqa: E402
from stockradar.jobs.resolve_core_csv import CORE_CSV_NAME  # noqa: E402
from stockradar.storage.control_plane import (  # noqa: E402
    build_patched_object_keys,
    normalize_rollout_stage,
    resolve_fixed_object_key,
    resolve_patched_r2_keys,
    supabase_commit_is_fatal,
)
from stockradar.storage.mapping_catalog import get_entry, load_mapping  # noqa: E402
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


def _rollout_stage(args: argparse.Namespace) -> str:
    if getattr(args, "phase3_rollout_stage", None):
        return normalize_rollout_stage(args.phase3_rollout_stage)
    env = os.environ.get("PHASE3_ROLLOUT_STAGE", "").strip()
    if env:
        return normalize_rollout_stage(env)
    mapping = load_mapping()
    return normalize_rollout_stage(str(mapping.get("phase3_rollout_stage") or "3a"))


def _cache_key_for_entry(entry_id: str) -> str:
    entry = get_entry(entry_id)
    return str(entry["source_name_pattern"])


def cmd_put_fixed(args: argparse.Namespace) -> int:
    stage = _rollout_stage(args)
    fatal = supabase_commit_is_fatal(stage)
    is_replay = str(args.is_replay).strip().lower() in ("true", "1", "yes")

    if is_replay:
        _emit(
            {
                "status": "skipped",
                "replay_save_skipped": True,
                "supabase_commit_ok": False,
                "cache_source": "none",
            },
            args.json_output,
        )
        return 0

    local_path = Path(args.local_path)
    if not local_path.is_file():
        print(f"error: missing local file: {local_path}", file=sys.stderr)
        return 1

    entry = get_entry(args.entry_id)
    cache_key = _cache_key_for_entry(args.entry_id)
    object_key = resolve_fixed_object_key(args.entry_id, str(entry.get("target_r2_key_pattern") or ""))
    content = local_path.read_bytes()
    sha256 = compute_sha256(str(local_path))
    size_bytes = len(content)
    writer = str(entry.get("writer_workflow") or "daily.yml")
    run_id = int(args.github_run_id)

    supabase = _adapter_supabase()
    pending_id: str | None = None
    if supabase is not None:
        try:
            pending = supabase.insert_cache_index_pending_fixed(
                cache_key=cache_key,
                object_key=object_key,
                sha256=sha256,
                size_bytes=size_bytes,
                writer_workflow=writer,
                source_github_run_id=run_id,
            )
            pending_id = str(pending["id"])
        except Exception as exc:
            _emit(
                {
                    "status": "error",
                    "supabase_commit_ok": False,
                    "supabase_commit_failed": f"pending_insert: {exc}",
                },
                args.json_output,
            )
            print(f"error: cache_index pending failed: {exc}", file=sys.stderr)
            return 1 if fatal else 0

    try:
        _r2().put_object(object_key, content, content_type="application/zip")
    except Exception as exc:
        if pending_id and supabase is not None:
            try:
                supabase.mark_cache_index_orphan(cache_index_id=pending_id)
            except Exception:
                pass
        print(f"error: R2 put failed: {exc}", file=sys.stderr)
        return 1

    if supabase is None:
        _emit(
            {
                "status": "ok",
                "cache_source": "r2",
                "supabase_commit_ok": False,
                "supabase_commit_failed": "supabase_not_configured",
            },
            args.json_output,
        )
        return 1 if fatal else 0

    try:
        supabase.commit_fixed_cache_rpc(
            cache_key=cache_key,
            object_key=object_key,
            sha256=sha256,
            size_bytes=size_bytes,
            writer_workflow=writer,
            source_github_run_id=run_id,
            history_id=pending_id,
        )
        _emit(
            {
                "status": "ok",
                "cache_source": "r2",
                "supabase_commit_ok": True,
                "warm_cache_key": cache_key,
                "object_key": object_key,
            },
            args.json_output,
        )
        return 0
    except Exception as exc:
        if pending_id:
            try:
                supabase.mark_cache_index_orphan(cache_index_id=pending_id)
            except Exception:
                pass
        _emit(
            {
                "status": "error",
                "cache_source": "r2",
                "supabase_commit_ok": False,
                "supabase_commit_failed": str(exc),
            },
            args.json_output,
        )
        print(f"error: commit_fixed_cache RPC failed: {exc}", file=sys.stderr)
        return 1 if fatal else 0


def cmd_get_fixed(args: argparse.Namespace) -> int:
    cache_key = _cache_key_for_entry(args.entry_id)
    local_path = Path(args.local_path)
    supabase = _adapter_supabase()
    if supabase is None:
        _emit({"status": "miss", "cache_source": None, "reason": "supabase_not_configured"}, args.json_output)
        return 1

    pointer = supabase.get_cache_pointer(cache_key=cache_key)
    if pointer is None:
        _emit({"status": "miss", "cache_source": None, "reason": "cache_pointer_missing"}, args.json_output)
        return 1

    object_key = str(pointer["object_key"])
    try:
        content = _r2().get_object(object_key)
    except Exception as exc:
        _emit({"status": "miss", "cache_source": None, "reason": str(exc)}, args.json_output)
        return 1

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    _emit(
        {
            "status": "ok",
            "cache_source": "r2",
            "warm_cache_key": cache_key,
            "object_key": object_key,
        },
        args.json_output,
    )
    return 0


def cmd_put_patched(args: argparse.Namespace) -> int:
    stage = _rollout_stage(args)
    fatal = supabase_commit_is_fatal(stage)

    csv_path = Path(args.csv_path)
    manifest_path = Path(args.manifest_path)
    if not csv_path.is_file() or not manifest_path.is_file():
        print("error: patched csv/manifest missing", file=sys.stderr)
        return 1

    cache_key = args.cache_key
    monthly_tag = args.monthly_tag
    run_date = args.run_date
    csv_key, manifest_key = resolve_patched_r2_keys(monthly_tag=monthly_tag, run_date=run_date)
    csv_bytes = csv_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    csv_sha = compute_sha256(str(csv_path))
    manifest_sha = compute_sha256(str(manifest_path))
    object_keys = build_patched_object_keys(
        csv_object_key=csv_key,
        csv_sha256=csv_sha,
        csv_size_bytes=len(csv_bytes),
        manifest_object_key=manifest_key,
        manifest_sha256=manifest_sha,
        manifest_size_bytes=len(manifest_bytes),
    )

    supabase = _adapter_supabase()
    row_id: str | None = None
    if supabase is not None:
        try:
            pending = supabase.upsert_cache_index_pending_patched(
                cache_key=cache_key,
                object_keys=object_keys,
                sha256=csv_sha,
                size_bytes=len(csv_bytes),
                writer_workflow="daily_universe_patch.yml",
                source_github_run_id=int(args.github_run_id),
                source_ref=args.source_ref,
            )
            row_id = str(pending["id"])
        except Exception as exc:
            _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)}, args.json_output)
            return 1 if fatal else 0

    try:
        _r2().put_object(csv_key, csv_bytes, content_type="text/csv")
        _r2().put_object(manifest_key, manifest_bytes, content_type="application/json")
    except Exception as exc:
        if row_id and supabase is not None:
            try:
                supabase.mark_cache_index_orphan(cache_index_id=row_id)
            except Exception:
                pass
        print(f"error: R2 patched put failed: {exc}", file=sys.stderr)
        return 1

    if supabase is None:
        _emit({"status": "ok", "supabase_commit_ok": False}, args.json_output)
        return 1 if fatal else 0

    try:
        supabase.commit_cache_index_patched(
            cache_index_id=row_id or "",
            object_keys=object_keys,
            sha256=csv_sha,
            size_bytes=len(csv_bytes),
        )
        _emit({"status": "ok", "supabase_commit_ok": True, "cache_key": cache_key}, args.json_output)
        return 0
    except Exception as exc:
        if row_id:
            try:
                supabase.mark_cache_index_orphan(cache_index_id=row_id)
            except Exception:
                pass
        _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)}, args.json_output)
        return 1 if fatal else 0


def cmd_get_patched(args: argparse.Namespace) -> int:
    patched_dir = Path(args.patched_dir)
    supabase = _adapter_supabase()
    if supabase is None:
        print("error: supabase not configured", file=sys.stderr)
        return 1

    key = args.cache_key
    full_row = supabase.get_patched_cache_row(cache_key=key)
    if full_row is None:
        _emit({"status": "miss", "reason": "cache_key_not_in_index"}, args.json_output)
        return 1

    object_keys = full_row.get("object_keys")
    if not isinstance(object_keys, dict):
        print("error: object_keys missing", file=sys.stderr)
        return 1

    csv_spec = object_keys["csv"]
    manifest_spec = object_keys["manifest"]
    csv_bytes = _r2().get_object(str(csv_spec["object_key"]))
    manifest_bytes = _r2().get_object(str(manifest_spec["object_key"]))

    patched_dir.mkdir(parents=True, exist_ok=True)
    csv_out = patched_dir / CORE_CSV_NAME
    manifest_out = patched_dir / MANIFEST_FILENAME
    csv_out.write_bytes(csv_bytes)
    manifest_out.write_bytes(manifest_bytes)

    if csv_spec.get("sha256"):
        if compute_sha256(str(csv_out)) != csv_spec["sha256"]:
            print("error: patched csv sha256 mismatch", file=sys.stderr)
            return 1
    if manifest_spec.get("sha256"):
        if compute_sha256(str(manifest_out)) != manifest_spec["sha256"]:
            print("error: patched manifest sha256 mismatch", file=sys.stderr)
            return 1

    _emit({"status": "ok", "cache_source": "r2", "cache_key": key}, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Warm cache bus CLI (Phase 3).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--phase3-rollout-stage", default=None)
    common.add_argument("--json-output", default=None)

    p_pf = sub.add_parser("put-fixed", parents=[common])
    p_pf.add_argument("--entry-id", required=True)
    p_pf.add_argument("--local-path", required=True)
    p_pf.add_argument("--github-run-id", required=True)
    p_pf.add_argument("--is-replay", required=True)

    p_gf = sub.add_parser("get-fixed", parents=[common])
    p_gf.add_argument("--entry-id", required=True)
    p_gf.add_argument("--local-path", required=True)

    p_pp = sub.add_parser("put-patched", parents=[common])
    p_pp.add_argument("--cache-key", required=True)
    p_pp.add_argument("--monthly-tag", required=True)
    p_pp.add_argument("--run-date", required=True)
    p_pp.add_argument("--csv-path", required=True)
    p_pp.add_argument("--manifest-path", required=True)
    p_pp.add_argument("--github-run-id", required=True)
    p_pp.add_argument("--source-ref", required=True)

    p_gp = sub.add_parser("get-patched", parents=[common])
    p_gp.add_argument("--cache-key", required=True)
    p_gp.add_argument("--monthly-tag", required=True)
    p_gp.add_argument("--run-date", required=True)
    p_gp.add_argument("--patched-dir", default="data/universe/jpx/patched_cache")

    args = parser.parse_args(argv)
    if args.cmd == "put-fixed":
        sys.exit(cmd_put_fixed(args))
    if args.cmd == "get-fixed":
        sys.exit(cmd_get_fixed(args))
    if args.cmd == "get-patched":
        sys.exit(cmd_get_patched(args))
    if args.cmd == "put-patched":
        sys.exit(cmd_put_patched(args))
    parser.error("unknown command")


if __name__ == "__main__":
    main()
