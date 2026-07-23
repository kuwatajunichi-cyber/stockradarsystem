"""Generate Phase 4.5 budget fixtures and report JSON (deterministic, Secrets-free)."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from stockradar.storage.phase45_budget import (
    BUDGET_SCHEMA_VERSION,
    extrapolate_r2_five_years,
    extrapolate_supabase_latest_rows,
    within_free_tier,
)

DEFAULT_SEED = 42


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


def _logical_digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_daily_parquet_bytes(
    *,
    symbols: int,
    metrics: int,
    trading_days: int,
    seed: int,
) -> tuple[bytes, str]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=date.today(), periods=trading_days)
    rows = []
    for sym_idx in range(symbols):
        code = f"{7200 + sym_idx:04d}"
        for d in dates:
            row = {"instrument_code": code, "trade_date": d.date().isoformat()}
            for m in range(metrics):
                row[f"metric_{m:02d}"] = float(rng.uniform(0, 100))
            rows.append(row)
    df = pd.DataFrame(rows)
    path = Path("_tmp_bench.parquet")
    try:
        df.to_parquet(path, index=False)
        data = path.read_bytes()
    finally:
        if path.exists():
            path.unlink()
    digest = _logical_digest({"rows": len(df), "cols": list(df.columns), "seed": seed})
    return len(data), digest


def generate_series_gzip_bytes(*, trading_days: int, metrics: int, seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(trading_days - 1, -1, -1)]
    series = {
        f"metric_{m:02d}": [float(v) for v in rng.uniform(0.0, 100.0, size=trading_days)]
        for m in range(metrics)
    }
    payload = {"dates": dates, "series": series, "seed": seed}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=9, mtime=0)


def build_report(
    *,
    scale: str,
    symbols: int,
    metrics: int,
    trading_days: int,
    seed: int,
    layer1_r2_bytes: int = 0,
) -> dict:
    parquet_bytes, parquet_digest = generate_daily_parquet_bytes(
        symbols=symbols, metrics=metrics, trading_days=trading_days, seed=seed
    )
    series_bytes = generate_series_gzip_bytes(trading_days=trading_days, metrics=metrics, seed=seed)
    series_total = len(series_bytes) * symbols
    r2_one_year = parquet_bytes + series_total
    r2_total = extrapolate_r2_five_years(one_year_bytes=r2_one_year) + layer1_r2_bytes
    latest_row_bytes = 512
    supabase_projection = extrapolate_supabase_latest_rows(row_bytes=latest_row_bytes, n_rows=symbols)
    ok, reasons = within_free_tier(
        supabase_projection_bytes=supabase_projection,
        r2_total_bytes=r2_total,
    )
    notes = list(reasons)
    if layer1_r2_bytes == 0:
        notes.append(
            "layer1_r2: 0 (deferred — pass --layer1-r2-bytes from Layer 1 PoC for full-scale budget)"
        )
    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        "generator_git_sha": _git_sha(),
        "generator_seed": seed,
        "scale": scale,
        "counts": {
            "symbols": symbols,
            "metrics": metrics,
            "trading_days": trading_days,
            "latest_rows": symbols,
        },
        "bytes": {
            "snapshots_parquet_total": parquet_bytes,
            "series_gzip_total": series_total,
            "r2_one_year": r2_one_year,
            "r2_total": r2_total,
            "latest_projection": supabase_projection,
            "layer1_r2": layer1_r2_bytes,
        },
        "digests": {"parquet_logical": parquet_digest},
        "verdict": {"within_free_tier": ok, "notes": notes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4.5 budget bench")
    parser.add_argument("--scale", choices=("ci", "full"), default="ci")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--layer1-r2-bytes",
        type=int,
        default=0,
        help="Layer 1 R2 bytes to add (0 = deferred; use PoC report for full scale)",
    )
    args = parser.parse_args(argv)
    if args.scale == "ci":
        symbols, metrics, trading_days = 30, 30, 25
    else:
        symbols, metrics, trading_days = 3000, 30, 250
    report = build_report(
        scale=args.scale,
        symbols=symbols,
        metrics=metrics,
        trading_days=trading_days,
        seed=args.seed,
        layer1_r2_bytes=args.layer1_r2_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "within_free_tier": report["verdict"]["within_free_tier"]}))
    return 0 if report["verdict"]["within_free_tier"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
