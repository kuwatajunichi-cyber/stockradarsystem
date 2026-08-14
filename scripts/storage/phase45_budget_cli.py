"""Phase 4.5 budget v2 CLI - Path B capacity report (Secrets-free)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from stockradar.storage.phase45_budget import (
    BUDGET_SCHEMA_VERSION,
    DEFAULT_BUDGET_AS_OF_DATE,
    DEFAULT_BUDGET_SEED,
    DEFAULT_PATH_B_CATALOG,
    DEFAULT_PRODUCTION_SYMBOLS,
    build_budget_v2_report,
    build_path_b_projection_inputs,
    project_r2_budget_v2,
)


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out[:40] if out else "unknown"
    except Exception:
        return "unknown"


def cmd_report_v2(args: argparse.Namespace) -> int:
    as_of_date = date.fromisoformat(args.as_of_date)
    inputs = build_path_b_projection_inputs(
        repo_root=_REPO_ROOT,
        symbols=args.symbols,
        seed=args.seed,
        as_of_date=as_of_date,
        catalog=args.catalog,
        retention_years=args.retention_years,
        metric_set_versions=args.metric_set_versions,
        include_layer1=not args.no_layer1,
    )
    breakdown = project_r2_budget_v2(inputs)
    report = build_budget_v2_report(
        inputs=inputs,
        breakdown=breakdown,
        generator_git_sha=_git_sha(),
        generator_seed=args.seed,
        as_of_date=as_of_date,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "ok",
                "schema_version": BUDGET_SCHEMA_VERSION,
                "within_free_tier": report["verdict"]["within_free_tier"],
                "r2_total": report["bytes"]["r2_total"],
                "report_hash": report["report_hash"],
            }
        )
    )
    return 0 if report["verdict"]["within_free_tier"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4.5 budget v2 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    report = sub.add_parser("report-v2", help="Generate Path B capacity report JSON")
    report.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "docs/operations/evidence/phase45_budget_v2_path_b_report.json",
    )
    report.add_argument("--symbols", type=int, default=DEFAULT_PRODUCTION_SYMBOLS)
    report.add_argument("--seed", type=int, default=DEFAULT_BUDGET_SEED)
    report.add_argument("--as-of-date", default=DEFAULT_BUDGET_AS_OF_DATE.isoformat())
    report.add_argument("--catalog", default=DEFAULT_PATH_B_CATALOG)
    report.add_argument("--retention-years", type=int, default=3)
    report.add_argument("--metric-set-versions", type=int, default=2)
    report.add_argument("--no-layer1", action="store_true")
    report.set_defaults(func=cmd_report_v2)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
