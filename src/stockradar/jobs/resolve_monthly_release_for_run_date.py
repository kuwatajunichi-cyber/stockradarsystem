"""CLI wrapper: resolve monthly tag via GitHub release tags file (legacy entry)."""
from __future__ import annotations

import sys

from stockradar.jobs.resolve_monthly_for_run_date import main as _main


def main(argv: list[str] | None = None) -> None:
    forwarded = list(argv) if argv is not None else sys.argv[1:]
    if "--source" not in forwarded:
        forwarded = ["--source", "github", *forwarded]
    _main(forwarded)


if __name__ == "__main__":
    main()
