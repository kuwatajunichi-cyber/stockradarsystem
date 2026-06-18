#!/usr/bin/env python3
"""Manual Phase 1 smoke: GitHub dispatch token + optional Cloudflare account check.

Not part of CI required checks. Never prints secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _gh_token() -> str | None:
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
        token = out.stdout.strip()
        return token or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _github_dispatch_probe(token: str, owner: str, repo: str, live: bool) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/daily.yml/dispatches"
    body = {"ref": os.environ.get("GITHUB_REF", "main")}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "stockradar-phase1-smoke",
        },
    )
    if not live:
        return {"skipped": True, "reason": "live_dispatch_disabled", "endpoint": url}
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.reason}


def _cloudflare_account_probe() -> dict:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        return {
            "skipped": True,
            "reason": "missing_cloudflare_credentials",
            "blocker": True,
        }
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "stockradar-phase1-smoke",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": payload.get("success", False), "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.reason}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 Cloudflare/GitHub dispatch smoke")
    parser.add_argument(
        "--live-dispatch",
        action="store_true",
        help="Actually POST workflow_dispatch (requires LIVE_DISPATCH_ENABLED=true)",
    )
    args = parser.parse_args()

    _load_dotenv()
    owner = os.environ.get("GITHUB_OWNER", "kuwatajunichi-cyber")
    repo = os.environ.get("GITHUB_REPO", "stockradarsystem")

    token = os.environ.get("GH_DISPATCH_TOKEN", "").strip() or _gh_token()
    if not token:
        print(json.dumps({"github": {"ok": False, "error": "no_token"}}))
        return 1

    live = args.live_dispatch and os.environ.get("LIVE_DISPATCH_ENABLED", "").lower() == "true"
    github_result = _github_dispatch_probe(token, owner, repo, live=live)
    cf_result = _cloudflare_account_probe()

    report = {"github": github_result, "cloudflare": cf_result}
    print(json.dumps(report, indent=2))

    if cf_result.get("blocker"):
        return 2
    if github_result.get("ok") is False:
        return 1
    if live and not github_result.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
