"""Backfill web-asof bundles for the last N as-of dates that have committed enriched CSV.

Uses the active metric_set UUID. Does not CAS.
R2 staging retention may drop enriched CSV; this CLI opts into OHLC-universe fallback.
Daily assemble does not.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.storage.r2_client import _load_dotenv  # noqa: E402
from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402
from scripts.storage.web_asof_assemble_cli import (  # noqa: E402
    _adapter_supabase,
    _download_enriched_csv,
    cmd_assemble,
)

_load_dotenv()

_PRECOMMITTED = {"2026-10-02": "already_committed_e31b9be8"}


def _committed_as_ofs(limit: int) -> list[str]:
    from stockradar.storage.supabase_client import SupabaseRestAdapter

    client = SupabaseRestAdapter.from_env()
    resp = client._request(
        "GET",
        "/rest/v1/artifact_index",
        params={
            "object_key": "like.*indicators_event_enriched_*",
            "status": "eq.committed",
            "select": "object_key,committed_at_utc",
            "order": "committed_at_utc.desc",
            "limit": "400",
        },
    )
    resp.raise_for_status()
    seen: list[str] = []
    for row in resp.json() or []:
        key = str(row.get("object_key") or "")
        marker = "indicators_event_enriched_"
        idx = key.rfind(marker)
        if idx < 0:
            continue
        compact = key[idx + len(marker) : idx + len(marker) + 8]
        if len(compact) != 8 or not compact.isdigit():
            continue
        as_of = f"{compact[0:4]}-{compact[4:6]}-{compact[6:8]}"
        try:
            date.fromisoformat(as_of)
        except ValueError:
            continue
        if as_of not in seen:
            seen.append(as_of)
        if len(seen) >= limit:
            break
    return seen


def _put_ok(work_dir: Path, as_of: str) -> bool:
    path = work_dir / f"put_{as_of}.json"
    if not path.is_file():
        return False
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return prev.get("exit_code") == 0 or prev.get("status") == "ok"


def _as_of_done(work_dir: Path, as_of: str) -> bool:
    return as_of in _PRECOMMITTED or _put_ok(work_dir, as_of)


def backfill_coverage_status(
    *,
    requested: int,
    found: int,
    remaining: list[str],
) -> tuple[str, int]:
    """Report coverage honestly. Short candidate lists are not_met, not ok."""
    if remaining:
        return "error", 1
    if found < requested:
        return "not_met", 1
    return "ok", 0


def _assemble_one(
    *,
    as_of: str,
    work_dir: Path,
    github_run_id: int,
    put: bool,
    skip_download: bool,
) -> int:
    ohlc_zip = work_dir / "ohlc_store.zip"
    if skip_download:
        supabase = _adapter_supabase()
        r2 = R2StagingAdapter()
        _download_enriched_csv(
            supabase,
            r2,
            as_of,
            work_dir / "enriched.csv",
            ohlc_zip=ohlc_zip,
            allow_ohlc_universe_fallback=True,
        )
    ns = argparse.Namespace(
        as_of=as_of,
        work_dir=work_dir,
        github_run_id=github_run_id,
        repository="local-ops-web-asof-backfill",
        workflow="ops-web-asof-backfill",
        codes="",
        put=put,
        require_enabled=False,
        skip_download=skip_download,
        skip_freeze=False,
        allow_ohlc_universe_fallback=True,
        json_output=work_dir / f"put_{as_of}.json",
    )
    return cmd_assemble(ns)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill web-asof as-of windows.")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--github-run-id", type=int, default=0)
    parser.add_argument("--put", action="store_true")
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--max-passes", type=int, default=8)
    parser.add_argument("--retries-per-as-of", type=int, default=3)
    args = parser.parse_args(argv)
    dates = _committed_as_ofs(args.limit)
    if len(dates) < 1:
        print(json.dumps({"status": "error", "reason": "no_enriched_as_of"}, ensure_ascii=False))
        return 2

    results: list[dict] = []
    exit_code = 0
    for pass_i in range(max(1, args.max_passes)):
        remaining = [as_of for as_of in dates if not _as_of_done(args.work_dir, as_of)]
        print(
            json.dumps(
                {
                    "pass": pass_i + 1,
                    "remaining": len(remaining),
                    "done": len(dates) - len(remaining),
                    "total": len(dates),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if not remaining:
            exit_code = 0
            break
        progressed = False
        for as_of in remaining:
            skip_download = (args.work_dir / "ohlc_store.zip").is_file()
            last_error: str | None = None
            code = 1
            for attempt in range(max(1, args.retries_per_as_of)):
                try:
                    code = _assemble_one(
                        as_of=as_of,
                        work_dir=args.work_dir,
                        github_run_id=args.github_run_id,
                        put=args.put,
                        skip_download=skip_download,
                    )
                    last_error = None
                    if code == 0:
                        break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    print(
                        json.dumps(
                            {
                                "as_of": as_of,
                                "attempt": attempt + 1,
                                "error": last_error[:400],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    traceback.print_exc()
                    code = 1
            row: dict = {"as_of": as_of, "exit_code": code}
            put_path = args.work_dir / f"put_{as_of}.json"
            if put_path.is_file():
                try:
                    row["result"] = json.loads(put_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    row["result"] = None
            if last_error:
                row["error"] = last_error[:400]
            results.append(row)
            if code == 0:
                progressed = True
            else:
                exit_code = code
        if not progressed:
            break

    remaining = [as_of for as_of in dates if not _as_of_done(args.work_dir, as_of)]
    status, exit_code = backfill_coverage_status(
        requested=args.limit,
        found=len(dates),
        remaining=remaining,
    )
    payload = {
        "status": status,
        "exit_code": exit_code,
        "requested": args.limit,
        "found": len(dates),
        "remaining": remaining,
        "as_ofs": dates,
        "results": results[-80:],
    }
    text = json.dumps(payload, ensure_ascii=False)
    print(text[:4000])
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
