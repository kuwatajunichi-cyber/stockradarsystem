"""Phase 4.5 Free-tier budget thresholds and aggregation (ADR-004)."""
from __future__ import annotations

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
