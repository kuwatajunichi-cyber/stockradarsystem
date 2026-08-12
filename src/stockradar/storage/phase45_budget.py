"""Phase 4.5 Free-tier budget thresholds and aggregation (ADR-004)."""
from __future__ import annotations

import io
import zipfile
from datetime import date

import numpy as np
import pandas as pd

# Supabase database bytes
SUPABASE_WARN_BYTES = 350 * 1024 * 1024
SUPABASE_CLEANUP_BYTES = 400 * 1024 * 1024
SUPABASE_HARD_LIMIT_BYTES = 500 * 1024 * 1024

# R2 storage bytes
R2_WARN_BYTES = 8 * 1024 * 1024 * 1024
R2_CLEANUP_BYTES = 9 * 1024 * 1024 * 1024

# Monthly operation planning limits (80% of free tier)
R2_CLASS_A_MONTHLY_PLAN = 800_000
R2_CLASS_B_MONTHLY_PLAN = 8_000_000
SUPABASE_EGRESS_MONTHLY_PLAN_BYTES = int(4 * 1024 * 1024 * 1024)

BUDGET_SCHEMA_VERSION = 1


def within_free_tier(
    *,
    supabase_projection_bytes: int,
    r2_total_bytes: int,
) -> tuple[bool, list[str]]:
    """Return (pass, reasons). Warning exceed => fail for preflight closed."""
    reasons: list[str] = []
    ok = True
    if supabase_projection_bytes >= SUPABASE_WARN_BYTES:
        ok = False
        reasons.append(
            f"supabase_projection {supabase_projection_bytes} >= warn {SUPABASE_WARN_BYTES}"
        )
    if r2_total_bytes >= R2_WARN_BYTES:
        ok = False
        reasons.append(f"r2_total {r2_total_bytes} >= warn {R2_WARN_BYTES}")
    return ok, reasons


def extrapolate_r2_five_years(*, one_year_bytes: int, metric_set_versions: int = 4) -> int:
    """Conservative R2 extrapolation: 5 years x metric set versions."""
    return one_year_bytes * 5 * metric_set_versions


def extrapolate_supabase_latest_rows(*, row_bytes: int, n_rows: int) -> int:
    """Latest projection only (not 90k EAV)."""
    return row_bytes * n_rows


_LAYER1_INDEX_SYMBOLS: tuple[str, ...] = ("^N225", "^TOPX")


def estimate_layer1_warm_cache_r2_bytes(
    *,
    symbols: int,
    retention_trading_days: int,
    seed: int = 42,
    as_of_date: date | None = None,
) -> int:
    """
    Deterministic zip-size estimate for Layer 1 warm caches (ohlc-store + index-store).

    Builds representative per-symbol CSV payloads and compresses them like archive jobs.
    Secrets-free; used by Layer 1 PoC and full-scale budget bench.
    """
    if symbols <= 0:
        raise ValueError("symbols must be positive")
    if retention_trading_days <= 0:
        raise ValueError("retention_trading_days must be positive")

    anchor = as_of_date or date(2026, 6, 30)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=anchor, periods=retention_trading_days)

    ohlc_buf = io.BytesIO()
    with zipfile.ZipFile(ohlc_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sym_idx in range(symbols):
            code = f"{7200 + sym_idx:04d}.T"
            df = pd.DataFrame(
                {
                    "Open": rng.uniform(100.0, 200.0, size=retention_trading_days),
                    "High": rng.uniform(100.0, 200.0, size=retention_trading_days),
                    "Low": rng.uniform(100.0, 200.0, size=retention_trading_days),
                    "Close": rng.uniform(100.0, 200.0, size=retention_trading_days),
                    "Volume": rng.integers(1000, 100_000, size=retention_trading_days),
                },
                index=dates,
            )
            zf.writestr(f"yf_daily/{code}.csv", df.to_csv(encoding="utf-8-sig"))

    index_buf = io.BytesIO()
    with zipfile.ZipFile(index_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in _LAYER1_INDEX_SYMBOLS:
            df = pd.DataFrame(
                {"Close": rng.uniform(1000.0, 3000.0, size=retention_trading_days)},
                index=dates,
            )
            zf.writestr(f"yf_index/{name}.csv", df.to_csv(encoding="utf-8-sig"))

    return len(ohlc_buf.getvalue()) + len(index_buf.getvalue())
