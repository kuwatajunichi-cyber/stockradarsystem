"""ADR-005 poller: claim MNC outbox and workflow_dispatch the worker via GH_DISPATCH_TOKEN."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseRestAdapter,
)


def _supabase():
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    return SupabaseRestAdapter.from_env()


def _claim_rows(adapter, *, limit: int, claimed_by: str) -> list[dict]:
    if isinstance(adapter, FakeSupabaseControlAdapter):
        return []
    resp = adapter._request(
        "POST",
        "/rest/v1/rpc/claim_mnc_outbox",
        json_body={"p_limit": limit, "p_claimed_by": claimed_by},
    )
    resp.raise_for_status()
    rows = resp.json()
    return list(rows) if isinstance(rows, list) else []


def _mark_dispatched(
    adapter,
    *,
    outbox_id: str,
    fencing_token: int,
    github_run_id: int,
) -> dict:
    if isinstance(adapter, FakeSupabaseControlAdapter):
        for row in adapter.mnc_outbox:
            if str(row.get("id")) != outbox_id:
                continue
            if int(row.get("fencing_token") or 0) != int(fencing_token):
                return {"ok": False, "reason": "fencing_mismatch"}
            row["status"] = "dispatched"
            row["github_run_id"] = int(github_run_id)
            return {"ok": True, "outbox_id": outbox_id}
        return {"ok": False, "reason": "not_found"}
    resp = adapter._request(
        "POST",
        "/rest/v1/rpc/mark_mnc_outbox_dispatched",
        json_body={
            "p_outbox_id": outbox_id,
            "p_fencing_token": int(fencing_token),
            "p_github_run_id": int(github_run_id),
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    return dict(payload) if isinstance(payload, dict) else {"ok": True}


def _dispatch_worker(
    *,
    token: str,
    repository: str,
    ref: str,
    workflow_file: str,
    request_id: str,
    outbox_id: str,
    fencing_token: str,
) -> None:
    if not token:
        raise RuntimeError("GH_DISPATCH_TOKEN required")
    owner, _, repo = repository.partition("/")
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/"
        f"{workflow_file}/dispatches"
    )
    body = json.dumps(
        {
            "ref": ref,
            "inputs": {
                "request_id": request_id,
                "outbox_id": outbox_id,
                "fencing_token": fencing_token,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status not in (201, 204):
                raise RuntimeError(f"dispatch status {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"dispatch failed: {exc.code} {detail}") from exc


def cmd_claim_and_dispatch(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_DISPATCH_TOKEN", "").strip()
    if not token:
        print("error: GH_DISPATCH_TOKEN required (GITHUB_TOKEN forbidden)", file=sys.stderr)
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    ref = os.environ.get("GITHUB_REF_NAME", "main").strip() or "main"
    if not repo:
        print("error: GITHUB_REPOSITORY required", file=sys.stderr)
        return 1
    adapter = _supabase()
    claimed_by = f"poller:{os.environ.get('GITHUB_RUN_ID', 'local')}"
    rows = _claim_rows(adapter, limit=int(args.limit), claimed_by=claimed_by)
    if not rows:
        print(json.dumps({"status": "ok", "claimed": 0}))
        return 0
    dispatched: list[str] = []
    for row in rows:
        request_id = str(row.get("request_id") or "")
        outbox_id = str(row.get("id") or "")
        fencing = str(row.get("fencing_token") or "0")
        _dispatch_worker(
            token=token,
            repository=repo,
            ref=ref,
            workflow_file=args.worker_workflow,
            request_id=request_id,
            outbox_id=outbox_id,
            fencing_token=fencing,
        )
        poller_run_id = int(os.environ.get("GITHUB_RUN_ID") or 0)
        mark = _mark_dispatched(
            adapter,
            outbox_id=outbox_id,
            fencing_token=int(fencing or 0),
            github_run_id=poller_run_id,
        )
        if mark.get("ok") is False and str(mark.get("reason") or "") == "fencing_mismatch":
            # Another owner claimed; dispatch already fired — record and continue.
            pass
        elif mark.get("ok") is False:
            raise RuntimeError(f"mark_mnc_outbox_dispatched failed: {mark}")
        dispatched.append(request_id)
    print(json.dumps({"status": "ok", "claimed": len(dispatched), "request_ids": dispatched}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MNC outbox poller")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("claim-and-dispatch")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--worker-workflow", default="monthly_new_core_backfill.yml")
    p.set_defaults(func=cmd_claim_and_dispatch)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
