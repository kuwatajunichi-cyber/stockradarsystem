"""Layer 1 backfill feasibility PoC (local temp only, no R2/Supabase writes)."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

from stockradar.config import compute_layer1_required_trading_days, compute_layer1_retention_trading_days
from stockradar.storage.phase45_budget import estimate_layer1_warm_cache_r2_bytes
from stockradar.utils.yf_cache_long_history import classify_history_eligibility, fetch_long_history

POC_FIXED_END = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
POC_FIXED_AS_OF_DATE = date(2026, 6, 30)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()[:40]
    except Exception:
        return "unknown"


def run_poc(
    *,
    required_trading_days: int,
    fetch_chunk,
    listing_ages: dict[str, int | None] | None = None,
    universe_symbols: int = 3000,
    layer1_seed: int = 42,
    history_end: datetime = POC_FIXED_END,
) -> dict:
    t0 = time.perf_counter()
    df = fetch_long_history(
        end=history_end,
        required_trading_days=required_trading_days,
        fetch_chunk=fetch_chunk,
    )
    elapsed = time.perf_counter() - t0
    n_bars = len(df)
    classification = classify_history_eligibility(n_bars, required_trading_days=required_trading_days)
    retention_trading_days = compute_layer1_retention_trading_days()
    layer1_r2_bytes = estimate_layer1_warm_cache_r2_bytes(
        symbols=universe_symbols,
        retention_trading_days=retention_trading_days,
        seed=layer1_seed,
        as_of_date=POC_FIXED_AS_OF_DATE,
    )
    return {
        "schema_version": 1,
        "generator_git_sha": _git_sha(),
        "required_trading_days": required_trading_days,
        "retention_trading_days": retention_trading_days,
        "history_end_utc": history_end.isoformat(),
        "fetched_bars": n_bars,
        "classification": classification,
        "wall_time_sec": round(elapsed, 3),
        "listing_ages": listing_ages or {},
        "layer1_r2_bytes": layer1_r2_bytes,
        "layer1_r2_estimate": {
            "universe_symbols": universe_symbols,
            "seed": layer1_seed,
            "as_of_date": POC_FIXED_AS_OF_DATE.isoformat(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4.5 Layer 1 backfill PoC")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--universe-symbols", type=int, default=3000)
    parser.add_argument("--layer1-seed", type=int, default=42)
    args = parser.parse_args(argv)

    import pandas as pd

    def fake_chunk(start, end):
        idx = pd.bdate_range(start=start.date(), end=end.date())
        if len(idx) == 0:
            return pd.DataFrame(
                columns=["Open", "High", "Low", "Close", "Volume"],
            )
        return pd.DataFrame(
            {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1000},
            index=idx,
        )

    report = run_poc(
        required_trading_days=compute_layer1_required_trading_days(),
        fetch_chunk=fake_chunk,
        universe_symbols=args.universe_symbols,
        layer1_seed=args.layer1_seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "classification": report["classification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
