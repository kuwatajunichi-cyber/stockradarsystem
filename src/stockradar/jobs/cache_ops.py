"""
Shared helpers for Actions cache rotation (should_rotate, gh cache delete).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence


def should_rotate_cache(*, is_replay: bool, job_success: bool) -> bool:
    return bool(job_success) and not is_replay


def gh_cache_delete(
    repo: str,
    key: str,
    *,
    gh_token: str | None = None,
    run: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    token = gh_token or env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    cmd = ["gh", "cache", "delete", key, "--repo", repo]
    if run is None:
        return subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    return run(cmd)


def _truthy_replay(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Actions cache helpers (GitHub Actions).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_del = sub.add_parser("delete-key", help="Delete one key (best-effort; warns on gh failure).")
    p_del.add_argument("--repo", required=True)
    p_del.add_argument("--key", required=True)

    p_rot = sub.add_parser(
        "rotate-delete",
        help="Delete only when should_rotate_cache(job_success=True) allows (non-replay).",
    )
    p_rot.add_argument("--repo", required=True)
    p_rot.add_argument("--key", required=True)
    p_rot.add_argument(
        "--is-replay",
        required=True,
        help="Workflow output (e.g. true/false); case-insensitive.",
    )

    args = parser.parse_args(argv)
    if args.cmd == "delete-key":
        proc = gh_cache_delete(args.repo, args.key)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            print(f"warning: gh cache delete returned {proc.returncode}: {err}", file=sys.stderr)
        sys.exit(0)

    is_replay = _truthy_replay(args.is_replay)
    if not should_rotate_cache(is_replay=is_replay, job_success=True):
        print("skip_delete_warm_cache: should_rotate_cache=false (replay or policy)")
        sys.exit(0)
    proc = gh_cache_delete(args.repo, args.key)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        print(f"warning: gh cache delete returned {proc.returncode}: {err}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
