"""Monthly snapshot bus CLI: R2 monthly/ namespace + Supabase monthly_snapshots."""
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

from stockradar.storage.mapping_catalog import load_mapping  # noqa: E402
from stockradar.storage.monthly_snapshot_manifest import (  # noqa: E402
    MONTHLY_CSV_NAMES,
    build_monthly_object_keys,
    build_monthly_snapshot_manifest,
    serialize_monthly_snapshot_manifest,
)
from stockradar.storage.monthly_new_core import (  # noqa: E402
    CommittedMonthlySnapshotRow,
    build_request_id_v1,
    canonical_json_sha256_v1,
    codes_from_core_csv_bytes,
    current_core_logical_digest,
    decide_monthly_backfill_outcome,
    previous_core_row_for_release_month,
    expected_trade_dates_from_committed_snapshots,
)
from stockradar.storage.phase4_rollout import (  # noqa: E402
    monthly_dual_write_enabled,
    monthly_read_allows_github_fallback,
    monthly_shadow_write_enabled,
    monthly_write_is_fatal,
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


def _should_write(stage: str) -> bool:
    return monthly_shadow_write_enabled(stage) or monthly_dual_write_enabled(stage)


def cmd_commit_snapshot(args: argparse.Namespace) -> int:
    stage = _stage(args)
    if not _should_write(stage):
        _emit({"status": "skipped", "reason": "monthly_write_disabled_for_stage"}, args.json_output)
        return 0

    fatal = monthly_write_is_fatal(stage)
    staging = Path(args.staging_dir)
    monthly_tag = args.monthly_tag
    snapshot_date = args.snapshot_date
    github_run_id = int(args.github_run_id)

    csv_specs: dict[str, tuple[Path, str, int]] = {}
    for csv_name in MONTHLY_CSV_NAMES:
        csv_path = staging / csv_name
        if not csv_path.is_file():
            print(f"error: missing csv: {csv_path}", file=sys.stderr)
            return 1 if fatal else 0
        sha = compute_sha256(str(csv_path))
        csv_specs[csv_name] = (csv_path, sha, csv_path.stat().st_size)

    manifest_body = build_monthly_snapshot_manifest(
        staging_dir=staging,
        monthly_tag=monthly_tag,
        github_run_id=github_run_id,
        snapshot_date=snapshot_date,
    )
    manifest_bytes = serialize_monthly_snapshot_manifest(manifest_body)
    manifest_sha = compute_sha256_bytes(manifest_bytes)

    object_keys = build_monthly_object_keys(
        monthly_tag=monthly_tag,
        ipo_sha256=csv_specs["equity_domestic_ipo_with_name.csv"][1],
        ipo_size=csv_specs["equity_domestic_ipo_with_name.csv"][2],
        illiquid_sha256=csv_specs["equity_domestic_illiquid_with_name.csv"][1],
        illiquid_size=csv_specs["equity_domestic_illiquid_with_name.csv"][2],
        core_sha256=csv_specs["equity_domestic_core_with_name.csv"][1],
        core_size=csv_specs["equity_domestic_core_with_name.csv"][2],
        manifest_sha256=manifest_sha,
        manifest_size=len(manifest_bytes),
    )

    supabase = _adapter_supabase()
    snapshot_id: str | None = None
    supabase_shadow_failed: str | None = None
    if supabase is not None:
        try:
            pending = supabase.insert_monthly_snapshot_pending(
                monthly_tag=monthly_tag,
                snapshot_date=snapshot_date,
                github_run_id=github_run_id,
                object_keys=object_keys,
                sha256=object_keys["core"]["sha256"],
            )
            snapshot_id = str(pending["id"])
            if str(pending.get("status") or "") == "committed":
                _emit(
                    {
                        "status": "ok",
                        "supabase_commit_ok": True,
                        "monthly_snapshot_id": snapshot_id,
                        "monthly_tag": monthly_tag,
                        "noop": True,
                    },
                    args.json_output,
                )
                return 0
        except Exception as exc:
            if fatal:
                _emit(
                    {"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)},
                    args.json_output,
                )
                return 1
            supabase_shadow_failed = str(exc)

    try:
        for key_name, csv_name in (
            ("ipo", "equity_domestic_ipo_with_name.csv"),
            ("illiquid", "equity_domestic_illiquid_with_name.csv"),
            ("core", "equity_domestic_core_with_name.csv"),
        ):
            path, _, _ = csv_specs[csv_name]
            _r2().put_object(
                str(object_keys[key_name]["object_key"]),
                path.read_bytes(),
                content_type="text/csv",
            )
        _r2().put_object(
            str(object_keys["manifest"]["object_key"]),
            manifest_bytes,
            content_type="application/json",
        )
    except Exception as exc:
        if snapshot_id and supabase is not None:
            try:
                supabase.mark_monthly_snapshot_orphan(snapshot_id=snapshot_id)
            except Exception:
                pass
        print(f"error: R2 monthly put failed: {exc}", file=sys.stderr)
        return 1 if fatal else 0

    if supabase is None or snapshot_id is None:
        payload: dict[str, object] = {
            "status": "ok",
            "supabase_commit_ok": False,
            "monthly_tag": monthly_tag,
            "object_keys": object_keys,
        }
        if supabase_shadow_failed:
            payload["supabase_shadow_failed"] = supabase_shadow_failed
        _emit(payload, args.json_output)
        return 1 if fatal else 0

    try:
        feature_start = supabase.get_adr005_feature_start_release_month()
        release_month = str(snapshot_date).strip()[:7]
        if not feature_start:
            committed = supabase.commit_monthly_snapshot(snapshot_id=snapshot_id)
            _emit(
                {
                    "status": "ok",
                    "supabase_commit_ok": True,
                    "monthly_snapshot_id": committed["id"],
                    "monthly_tag": monthly_tag,
                    "mnc_outcome": "deferred_feature_start_unset",
                },
                args.json_output,
            )
            return 0

        metric_set_version_id = (
            os.environ.get("ADR005_METRIC_SET_VERSION_ID", "").strip()
            or os.environ.get("PHASE4_5_ACTIVE_METRIC_SET_VERSION_ID", "").strip()
        )
        if not metric_set_version_id:
            raise RuntimeError("ADR005_METRIC_SET_VERSION_ID required when feature_start is set")

        core_path = csv_specs["equity_domestic_core_with_name.csv"][0]
        current_codes = codes_from_core_csv_bytes(core_path.read_bytes())
        committed_rows_raw = supabase.list_committed_monthly_snapshot_rows()
        committed_rows = [
            CommittedMonthlySnapshotRow(
                monthly_tag=str(r["monthly_tag"]),
                snapshot_date=str(r["snapshot_date"]),
                github_run_id=int(r["github_run_id"]),
                object_keys=r.get("object_keys") or {},
            )
            for r in committed_rows_raw
        ]
        prev_row = previous_core_row_for_release_month(release_month, committed_rows)
        previous_codes: list[str] | None = None
        if prev_row is not None:
            from stockradar.storage.monthly_new_core import core_object_key_from_row

            prev_key = core_object_key_from_row(prev_row)
            if not prev_key:
                raise RuntimeError("previous core object_key missing")
            previous_codes = codes_from_core_csv_bytes(_r2().get_object(prev_key))

        expected_trade_dates: list[str] = []
        expected_raw = os.environ.get("ADR005_EXPECTED_TRADE_DATES_JSON", "").strip()
        if expected_raw:
            expected_trade_dates = list(json.loads(expected_raw))
        else:
            expected_trade_dates = expected_trade_dates_from_committed_snapshots(
                supabase.list_committed_derived_snapshot_trade_dates(
                    metric_set_version_id=metric_set_version_id
                )
            )

        decision = decide_monthly_backfill_outcome(
            release_month=release_month,
            feature_start_release_month=feature_start,
            previous_row=prev_row,
            current_codes=current_codes,
            previous_codes=previous_codes,
            expected_trade_dates=expected_trade_dates,
        )
        core_digest = current_core_logical_digest(current_codes)
        added_list = list(decision.added_codes)
        added_digest = canonical_json_sha256_v1(sorted(added_list))
        dates_digest = canonical_json_sha256_v1(list(expected_trade_dates))
        prev_tag = decision.previous_monthly_tag or ""
        request_id = build_request_id_v1(
            release_month=release_month,
            previous_monthly_tag=prev_tag,
            current_core_logical_digest_hex=core_digest,
            metric_set_version_id=metric_set_version_id,
            added_codes=added_list,
        )
        result = supabase.commit_monthly_snapshot_with_backfill_request(
            snapshot_id=snapshot_id,
            release_month=release_month,
            request_id=request_id,
            metric_set_version_id=metric_set_version_id,
            previous_monthly_tag=decision.previous_monthly_tag,
            current_core_logical_digest=core_digest,
            added_codes=added_list,
            added_codes_digest=added_digest,
            partition_codes_digest=added_digest,
            expected_trade_dates=expected_trade_dates,
            expected_trade_dates_digest=dates_digest,
            calendar_version=os.environ.get("ADR005_CALENDAR_VERSION", "jpx_calendar_v1").strip()
            or "jpx_calendar_v1",
            outcome=decision.outcome,
            reason_code=decision.reason_code,
        )
        _emit(
            {
                "status": "ok",
                "supabase_commit_ok": True,
                "monthly_snapshot_id": result.get("snapshot_id") or snapshot_id,
                "monthly_tag": monthly_tag,
                "mnc_outcome": decision.outcome,
                "mnc_reason_code": decision.reason_code,
                "mnc_request_id": result.get("request_id"),
                "added_codes_count": len(added_list),
            },
            args.json_output,
        )
        return 0
    except Exception as exc:
        if snapshot_id:
            try:
                supabase.mark_monthly_snapshot_orphan(snapshot_id=snapshot_id)
            except Exception:
                pass
        _emit({"status": "error", "supabase_commit_ok": False, "supabase_commit_failed": str(exc)}, args.json_output)
        return 1 if fatal else 0


def compute_sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _fetch_csv_from_github(monthly_tag: str, variant: str, local_path: Path) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        print("error: GITHUB_REPOSITORY required for github fallback", file=sys.stderr)
        return 1
    filename = f"equity_domestic_{variant}_with_name.csv"
    import subprocess as sp
    proc = sp.run(
        [
            "gh",
            "release",
            "download",
            monthly_tag,
            "--pattern",
            filename,
            "--dir",
            str(local_path.parent),
            "--repo",
            repo,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(
            f"error: gh release download failed: {proc.stderr or proc.stdout}",
            file=sys.stderr,
        )
        return 1
    downloaded = local_path.parent / filename
    if not downloaded.is_file():
        print(f"error: github fallback csv missing: {downloaded}", file=sys.stderr)
        return 1
    if downloaded != local_path:
        downloaded.replace(local_path)
    return 0


def cmd_fetch_csv(args: argparse.Namespace) -> int:
    monthly_tag = args.monthly_tag
    variant = args.variant
    local_path = Path(args.local_path)
    key = f"monthly/{monthly_tag}/equity_domestic_{variant}_with_name.csv"
    source = str(getattr(args, "source", "r2") or "r2").strip().lower()
    if source == "github":
        rc = _fetch_csv_from_github(monthly_tag, variant, local_path)
        if rc == 0:
            _emit({"status": "ok", "source": "github", "local_path": str(local_path)}, args.json_output)
        return rc
    try:
        content = _r2().get_object(key)
    except Exception as exc:
        stage = _stage(args)
        if monthly_read_allows_github_fallback(stage):
            rc = _fetch_csv_from_github(monthly_tag, variant, local_path)
            if rc == 0:
                _emit(
                    {
                        "status": "ok",
                        "source": "github_fallback",
                        "object_key": key,
                        "local_path": str(local_path),
                    },
                    args.json_output,
                )
                return 0
        print(f"error: R2 get failed for {key}: {exc}", file=sys.stderr)
        return 1
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    _emit({"status": "ok", "object_key": key, "local_path": str(local_path)}, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Monthly snapshot bus CLI (Phase 4).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--phase4-rollout-stage", default=None)
    common.add_argument("--json-output", default=None)

    p_commit = sub.add_parser("commit-snapshot", parents=[common])
    p_commit.add_argument("--staging-dir", required=True)
    p_commit.add_argument("--monthly-tag", required=True)
    p_commit.add_argument("--snapshot-date", required=True, help="YYYY-MM-DD")
    p_commit.add_argument("--github-run-id", required=True)

    p_fetch = sub.add_parser("fetch-csv", parents=[common])
    p_fetch.add_argument("--monthly-tag", required=True)
    p_fetch.add_argument("--variant", choices=("ipo", "illiquid", "core"), default="core")
    p_fetch.add_argument("--local-path", required=True)
    p_fetch.add_argument("--source", default="r2", choices=("r2", "github"))

    args = parser.parse_args(argv)
    if args.cmd == "commit-snapshot":
        sys.exit(cmd_commit_snapshot(args))
    if args.cmd == "fetch-csv":
        sys.exit(cmd_fetch_csv(args))
    parser.error("unknown command")


if __name__ == "__main__":
    main()
