"""ADR-005 worker entry: load request and run series_only planner/progress."""
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

from stockradar.jobs.write_series_only_generation import (  # noqa: E402
    ensure_seed_catalog_or_block,
    plan_series_only_trade_date,
)
from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseRestAdapter,
)


def _adapter():
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    return SupabaseRestAdapter.from_env()


def _load_request(adapter, request_id: str) -> dict:
    if isinstance(adapter, FakeSupabaseControlAdapter):
        row = adapter.mnc_requests.get(request_id)
        if not row:
            raise RuntimeError(f"request not found: {request_id}")
        return dict(row)
    resp = adapter._request(
        "GET",
        "/rest/v1/monthly_new_core_backfill_requests",
        params={"id": f"eq.{request_id}", "select": "*"},
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"request not found: {request_id}")
    return dict(rows[0])


def cmd_run_request(args: argparse.Namespace) -> int:
    ensure_seed_catalog_or_block()
    adapter = _adapter()
    req = _load_request(adapter, args.request_id)
    status = str(req.get("status") or "")
    if status in {"completed", "noop", "blocked", "grandfather", "superseded", "paused"}:
        print(json.dumps({"status": "ok", "skipped": True, "request_status": status}))
        return 0
    codes = req.get("added_codes") or []
    if isinstance(codes, str):
        codes = json.loads(codes)
    expected_dates = req.get("expected_trade_dates") or []
    if isinstance(expected_dates, str):
        expected_dates = json.loads(expected_dates)
    last = req.get("last_committed_trade_date")
    remaining = [d for d in expected_dates if last is None or str(d) > str(last)]
    if not remaining:
        print(json.dumps({"status": "ok", "done": True, "reason": "no_remaining_trade_dates"}))
        return 0
    trade_date = str(remaining[0])
    plan = plan_series_only_trade_date(
        request_id=args.request_id,
        mode="series_seed",
        trade_date=trade_date,
        candidate_codes=[str(c) for c in codes],
        existing_dates_by_code={},
    )
    payload = {
        "status": "ok",
        "request_id": args.request_id,
        "trade_date": trade_date,
        "write_codes": list(plan.write_codes),
        "resolved_noop_codes": list(plan.resolved_noop_codes),
        "expected_object_count": plan.expected_object_count,
        "note": "Layer1+CAS write loop continues in subsequent worker iterations",
        "github_run_id": args.github_run_id,
        "github_actor": args.github_actor,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MNC series_seed worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run-request")
    p.add_argument("--request-id", required=True)
    p.add_argument("--outbox-id", default="")
    p.add_argument("--fencing-token", default="")
    p.add_argument("--github-run-id", default="0")
    p.add_argument("--github-actor", default="")
    p.set_defaults(func=cmd_run_request)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
