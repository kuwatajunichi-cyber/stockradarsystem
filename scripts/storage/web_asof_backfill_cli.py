"""Backfill web-asof bundles for the last N as-of dates that have committed enriched CSV.

Uses the active metric_set UUID. Does not CAS.
"""
from __future__ import annotations

import argparse
import json
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill web-asof as-of windows.")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--github-run-id", type=int, default=0)
    parser.add_argument("--put", action="store_true")
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args(argv)
    dates = _committed_as_ofs(args.limit)
    if len(dates) < 1:
        print(json.dumps({"status": "error", "reason": "no_enriched_as_of"}, ensure_ascii=False))
        return 2
    results: list[dict] = []
    exit_code = 0
    for i, as_of in enumerate(dates):
        if as_of == "2026-10-02":
            results.append(
                {
                    "as_of": as_of,
                    "exit_code": 0,
                    "skipped": "already_committed_e31b9be8",
                }
            )
            continue
        skip_download = i > 0 and (args.work_dir / "ohlc_store.zip").is_file()
        if skip_download:
            supabase = _adapter_supabase()
            r2 = R2StagingAdapter()
            _download_enriched_csv(supabase, r2, as_of, args.work_dir / "enriched.csv")
        ns = argparse.Namespace(
            as_of=as_of,
            work_dir=args.work_dir,
            github_run_id=args.github_run_id,
            repository="local-ops-web-asof-backfill",
            workflow="ops-web-asof-backfill",
            codes="",
            put=args.put,
            require_enabled=False,
            skip_download=skip_download,
            skip_freeze=False,
            json_output=args.work_dir / f"put_{as_of}.json",
        )
        code = cmd_assemble(ns)
        row = {"as_of": as_of, "exit_code": code}
        put_path = args.work_dir / f"put_{as_of}.json"
        if put_path.is_file():
            try:
                row["result"] = json.loads(put_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                row["result"] = None
        results.append(row)
        if code != 0:
            exit_code = code
            break
    payload = {
        "status": "ok" if exit_code == 0 else "error",
        "exit_code": exit_code,
        "requested": args.limit,
        "attempted": len(results),
        "as_ofs": dates,
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False)
    print(text[:4000])
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
