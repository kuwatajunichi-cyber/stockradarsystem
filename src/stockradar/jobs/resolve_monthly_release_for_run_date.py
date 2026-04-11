"""
Resolve monthly-* GitHub Release tag for run_date; print key=value lines.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from stockradar.universe.monthly_release_pick import pick_monthly_release


def _append_github_output(path: str | None, key: str, value: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def _escape_kv(s: str) -> str:
    return s.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resolve monthly-* release tag for run_date.")
    parser.add_argument("--run-date", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--tags-file",
        type=Path,
        required=True,
        help="One release tag per line",
    )
    args = parser.parse_args(argv)

    try:
        run_d = date.fromisoformat(args.run_date.strip())
    except ValueError:
        print(f"error: invalid --run-date: {args.run_date}", file=sys.stderr)
        sys.exit(1)

    if not args.tags_file.is_file():
        print(f"error: --tags-file not found: {args.tags_file}", file=sys.stderr)
        sys.exit(1)

    lines = [
        ln.strip()
        for ln in args.tags_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    try:
        pick = pick_monthly_release(run_d, lines)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    print(f"monthly_tag={pick.tag}")
    print(f"universe_resolution={pick.universe_resolution}")
    print(f"resolution_reason={pick.reason}")
    _append_github_output(gh_out, "monthly_tag", pick.tag)
    _append_github_output(gh_out, "universe_resolution", pick.universe_resolution)
    _append_github_output(gh_out, "resolution_reason", _escape_kv(pick.reason))


if __name__ == "__main__":
    main()