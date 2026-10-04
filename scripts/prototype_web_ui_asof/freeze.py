#!/usr/bin/env python3
"""Freeze as-of CSV + read-only OHLC caches into prototype SQLite."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from stockradar.prototype_web_ui_asof.freeze_core import FreezePaths, freeze_asof


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Prototype as-of freeze (not Track D)")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--as-of", type=str, required=True, help="YYYY-MM-DD")
    p.add_argument("--daily-cache", type=Path, default=_REPO / "data" / "cache" / "yf_daily")
    p.add_argument("--index-cache", type=Path, default=_REPO / "data" / "cache" / "yf_index")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--codes", type=str, default="", help="comma-separated; empty=all")
    p.add_argument("--fail-on-stale-symbol", action="store_true")
    p.add_argument("--reconcile-code", type=str, default="")
    p.add_argument("--keep-csv-metrics", action="store_true", help="do not overwrite metrics from cache")
    args = p.parse_args(argv)

    as_of = date.fromisoformat(args.as_of)
    codes = [c.strip().zfill(4) for c in args.codes.split(",") if c.strip()] or None
    paths = FreezePaths(
        csv_path=args.csv,
        daily_cache_dir=args.daily_cache,
        index_cache_dir=args.index_cache,
        out_sqlite=args.out,
    )
    try:
        meta = freeze_asof(
            paths,
            as_of=as_of,
            codes=codes,
            exclude_stale_symbols=not args.fail_on_stale_symbol,
            reconcile_code=(args.reconcile_code.strip().zfill(4) if args.reconcile_code.strip() else None),
            overwrite_metrics_from_cache=not args.keep_csv_metrics,
        )
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
