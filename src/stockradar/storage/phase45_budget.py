"""Phase 4.5 Free-tier budget thresholds and aggregation (ADR-004)."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

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

BUDGET_SCHEMA_VERSION_V1 = 1
BUDGET_SCHEMA_VERSION = 2

DEFAULT_PATH_B_RETENTION_YEARS = 3
DEFAULT_PATH_B_METRIC_SET_VERSIONS = 2
DEFAULT_PATH_B_CATALOG = "config/metrics/metric_set_v1_free.yaml"
DEFAULT_TRADING_DAYS_PER_YEAR = 250
DEFAULT_PRODUCTION_SYMBOLS = 3000
DEFAULT_BUDGET_SEED = 42
DEFAULT_BUDGET_AS_OF_DATE = date(2026, 6, 30)
DEFAULT_SUPERSEDED_FRACTION = 0.10
DEFAULT_ORPHAN_FRACTION = 0.05
DEFAULT_FAILED_FRACTION = 0.02
DEFAULT_SAFETY_FACTOR = 1.20
MIN_SAFETY_FACTOR = 1.20
DEFAULT_ROLLBACK_DAYS = 5
DEFAULT_FAILED_DAYS = 3
DEFAULT_RECONCILE_REPAIR_RATE = 0.05


@dataclass(frozen=True)
class BudgetProjectionInputs:
    symbols: int
    metrics: int
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR
    retention_years: int = DEFAULT_PATH_B_RETENTION_YEARS
    metric_set_versions: int = DEFAULT_PATH_B_METRIC_SET_VERSIONS
    snapshot_bytes_per_trade_date: int = 0
    series_bytes_per_symbol_year: int = 0
    snapshot_manifest_bytes_per_trade_date: int = 0
    series_manifest_bytes_per_symbol_year: int = 0
    superseded_fraction: float = DEFAULT_SUPERSEDED_FRACTION
    orphan_fraction: float = DEFAULT_ORPHAN_FRACTION
    failed_fraction: float = DEFAULT_FAILED_FRACTION
    safety_factor: float = DEFAULT_SAFETY_FACTOR
    rollback_days: int = DEFAULT_ROLLBACK_DAYS
    failed_days: int = DEFAULT_FAILED_DAYS
    reconcile_repair_rate: float = DEFAULT_RECONCILE_REPAIR_RATE
    layer1_r2_bytes: int = 0
    catalog: str = DEFAULT_PATH_B_CATALOG
    path: str = "B"


@dataclass(frozen=True)
class BudgetProjectionBreakdown:
    snapshots: int
    series: int
    superseded: int
    orphan: int
    failed: int
    layer1_r2: int
    subtotal_before_safety: int
    r2_total: int


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


_LAYER1_INDEX_FILES: tuple[str, ...] = ("topix.csv", "nikkei.csv")


def _synthetic_ohlc_frame(
    rng: np.random.Generator,
    dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    n = len(dates)
    return pd.DataFrame(
        {
            "Open": rng.uniform(100.0, 200.0, size=n),
            "High": rng.uniform(100.0, 200.0, size=n),
            "Low": rng.uniform(100.0, 200.0, size=n),
            "Close": rng.uniform(100.0, 200.0, size=n),
            "Volume": rng.integers(1000, 100_000, size=n),
        },
        index=dates,
    )


def estimate_layer1_warm_cache_r2_bytes(
    *,
    symbols: int,
    retention_trading_days: int,
    seed: int = 42,
    as_of_date: date | None = None,
) -> int:
    """
    Deterministic zip-size estimate for Layer 1 warm caches (ohlc-store + index-store).

    Matches archive layout: ``data/cache/yf_daily/{code}.csv`` and
    ``data/cache/yf_index/{topix,nikkei}.csv`` flattened into each zip root.
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
            code = f"{7200 + sym_idx:04d}"
            df = _synthetic_ohlc_frame(rng, dates)
            zf.writestr(f"{code}.csv", df.to_csv(encoding="utf-8-sig"))

    index_buf = io.BytesIO()
    with zipfile.ZipFile(index_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in _LAYER1_INDEX_FILES:
            df = _synthetic_ohlc_frame(rng, dates)
            zf.writestr(name, df.to_csv(encoding="utf-8-sig"))

    return len(ohlc_buf.getvalue()) + len(index_buf.getvalue())


def measure_snapshot_bytes_per_trade_date(
    *,
    symbols: int,
    metrics: int,
    seed: int = DEFAULT_BUDGET_SEED,
    as_of_date: date = DEFAULT_BUDGET_AS_OF_DATE,
) -> int:
    """Deterministic parquet size for one trade-date snapshot (all symbols)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=as_of_date, periods=1)
    rows = []
    for sym_idx in range(symbols):
        code = f"{7200 + sym_idx:04d}"
        row = {"instrument_code": code, "trade_date": dates[0].date().isoformat()}
        for m in range(metrics):
            row[f"metric_{m:02d}"] = float(rng.uniform(0, 100))
        rows.append(row)
    df = pd.DataFrame(rows)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        df.to_parquet(tmp_path, index=False)
        return len(tmp_path.read_bytes())
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def measure_series_bytes_per_symbol_year(
    *,
    metrics: int,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    seed: int = DEFAULT_BUDGET_SEED,
    as_of_date: date = DEFAULT_BUDGET_AS_OF_DATE,
) -> int:
    """Deterministic gzip JSON size for one symbol-year series projection."""
    rng = np.random.default_rng(seed)
    dates = [
        (as_of_date - timedelta(days=i)).isoformat()
        for i in range(trading_days_per_year - 1, -1, -1)
    ]
    series = {
        f"metric_{m:02d}": [float(v) for v in rng.uniform(0.0, 100.0, size=trading_days_per_year)]
        for m in range(metrics)
    }
    payload = {"as_of_date": as_of_date.isoformat(), "dates": dates, "series": series, "seed": seed}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return len(gzip.compress(raw, compresslevel=9, mtime=0))


def project_r2_budget_v2(inputs: BudgetProjectionInputs) -> BudgetProjectionBreakdown:
    """
    Path B plan formula: active snapshots + series (body+manifest), plus
    superseded/reconcile/failed overhead, then safety_factor >= 1.20.
    Layer 1 warm cache is additive before safety.
    """
    if inputs.symbols <= 0 or inputs.metrics <= 0:
        raise ValueError("symbols and metrics must be positive")
    if inputs.snapshot_bytes_per_trade_date <= 0 or inputs.series_bytes_per_symbol_year <= 0:
        raise ValueError("byte rate inputs must be positive")
    if inputs.safety_factor < MIN_SAFETY_FACTOR:
        raise ValueError(
            f"safety_factor {inputs.safety_factor} < AC-CAP minimum {MIN_SAFETY_FACTOR}"
        )

    snapshot_unit = (
        inputs.snapshot_bytes_per_trade_date + inputs.snapshot_manifest_bytes_per_trade_date
    )
    series_unit = (
        inputs.series_bytes_per_symbol_year + inputs.series_manifest_bytes_per_symbol_year
    )
    snapshots = (
        snapshot_unit
        * inputs.trading_days_per_year
        * inputs.retention_years
        * inputs.metric_set_versions
    )
    series = (
        series_unit
        * inputs.symbols
        * inputs.retention_years
        * inputs.metric_set_versions
    )
    superseded = series_unit * inputs.symbols * inputs.rollback_days * inputs.metric_set_versions
    full_generation = snapshot_unit + (series_unit * inputs.symbols)
    orphan = int(
        inputs.rollback_days
        * inputs.reconcile_repair_rate
        * inputs.metric_set_versions
        * full_generation
    )
    failed = int(inputs.failed_days * inputs.failed_fraction * full_generation)
    subtotal = snapshots + series + superseded + orphan + failed + inputs.layer1_r2_bytes
    r2_total = int(subtotal * inputs.safety_factor)
    return BudgetProjectionBreakdown(
        snapshots=snapshots,
        series=series,
        superseded=superseded,
        orphan=orphan,
        failed=failed,
        layer1_r2=inputs.layer1_r2_bytes,
        subtotal_before_safety=subtotal,
        r2_total=r2_total,
    )


def canonical_report_hash(report: dict[str, object]) -> str:
    """SHA-256 of canonical JSON excluding volatile generator fields."""
    payload = {
        key: value
        for key, value in report.items()
        if key not in {"generator_git_sha", "report_hash"}
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_metric_count_from_catalog(catalog_path: Path) -> int:
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    members = data.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError(f"catalog {catalog_path} has no members")
    return len(members)


def build_path_b_projection_inputs(
    *,
    repo_root: Path,
    symbols: int = DEFAULT_PRODUCTION_SYMBOLS,
    seed: int = DEFAULT_BUDGET_SEED,
    as_of_date: date = DEFAULT_BUDGET_AS_OF_DATE,
    catalog: str = DEFAULT_PATH_B_CATALOG,
    retention_years: int = DEFAULT_PATH_B_RETENTION_YEARS,
    metric_set_versions: int = DEFAULT_PATH_B_METRIC_SET_VERSIONS,
    include_layer1: bool = True,
) -> BudgetProjectionInputs:
    catalog_path = repo_root / catalog
    metrics = load_metric_count_from_catalog(catalog_path)
    snapshot_bytes = measure_snapshot_bytes_per_trade_date(
        symbols=symbols,
        metrics=metrics,
        seed=seed,
        as_of_date=as_of_date,
    )
    series_bytes = measure_series_bytes_per_symbol_year(
        metrics=metrics,
        seed=seed,
        as_of_date=as_of_date,
    )
    from stockradar.storage.derived_series import build_series_manifest_bytes
    from stockradar.storage.derived_snapshot import build_snapshot_manifest_bytes

    snapshot_manifest_bytes = len(
        build_snapshot_manifest_bytes(
            trade_date=as_of_date.isoformat(),
            metric_set_version_id="11111111-2222-3333-4444-555555555555",
            generation_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            logical_digest="a" * 64,
            object_sha256="b" * 64,
            object_size=snapshot_bytes,
            layer1_input_fingerprint="c" * 64,
            writer_workflow="derived_writer.yml",
            set_fingerprint="d" * 64,
            source_github_run_id=1,
            row_count=symbols,
            metric_keys_ordered=[f"metric_{i:02d}" for i in range(metrics)],
            mode="normal",
        )
    )
    series_manifest_bytes = len(
        build_series_manifest_bytes(
            instrument_code="1301",
            year=as_of_date.year,
            metric_set_version_id="11111111-2222-3333-4444-555555555555",
            generation_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            logical_digest="a" * 64,
            object_sha256="b" * 64,
            object_size=series_bytes,
            writer_workflow="derived_writer.yml",
            set_fingerprint="d" * 64,
            source_github_run_id=1,
            row_count=1,
            metric_keys_ordered=[f"metric_{i:02d}" for i in range(metrics)],
            mode="normal",
        )
    )
    layer1 = 0
    if include_layer1:
        layer1 = estimate_layer1_warm_cache_r2_bytes(
            symbols=symbols,
            retention_trading_days=772,
            seed=seed,
            as_of_date=as_of_date,
        )
    return BudgetProjectionInputs(
        symbols=symbols,
        metrics=metrics,
        retention_years=retention_years,
        metric_set_versions=metric_set_versions,
        snapshot_bytes_per_trade_date=snapshot_bytes,
        series_bytes_per_symbol_year=series_bytes,
        snapshot_manifest_bytes_per_trade_date=snapshot_manifest_bytes,
        series_manifest_bytes_per_symbol_year=series_manifest_bytes,
        safety_factor=DEFAULT_SAFETY_FACTOR,
        rollback_days=DEFAULT_ROLLBACK_DAYS,
        failed_days=DEFAULT_FAILED_DAYS,
        reconcile_repair_rate=DEFAULT_RECONCILE_REPAIR_RATE,
        layer1_r2_bytes=layer1,
        catalog=catalog,
        path="B",
    )


def build_budget_v2_report(
    *,
    inputs: BudgetProjectionInputs,
    breakdown: BudgetProjectionBreakdown,
    generator_git_sha: str = "unknown",
    generator_seed: int = DEFAULT_BUDGET_SEED,
    as_of_date: date = DEFAULT_BUDGET_AS_OF_DATE,
    supabase_projection_bytes: int | None = None,
) -> dict[str, object]:
    if supabase_projection_bytes is None:
        supabase_projection_bytes = extrapolate_supabase_latest_rows(
            row_bytes=512,
            n_rows=inputs.symbols,
        )
    ok, reasons = within_free_tier(
        supabase_projection_bytes=supabase_projection_bytes,
        r2_total_bytes=breakdown.r2_total,
    )
    report: dict[str, object] = {
        "schema_version": BUDGET_SCHEMA_VERSION,
        "path": inputs.path,
        "catalog": inputs.catalog,
        "generator_git_sha": generator_git_sha,
        "generator_seed": generator_seed,
        "as_of_date": as_of_date.isoformat(),
        "projection_inputs": asdict(inputs),
        "bytes": {
            "snapshots": breakdown.snapshots,
            "series": breakdown.series,
            "superseded": breakdown.superseded,
            "orphan": breakdown.orphan,
            "failed": breakdown.failed,
            "layer1_r2": breakdown.layer1_r2,
            "subtotal_before_safety": breakdown.subtotal_before_safety,
            "r2_total": breakdown.r2_total,
            "latest_projection": supabase_projection_bytes,
        },
        "verdict": {"within_free_tier": ok, "notes": reasons},
    }
    report["report_hash"] = canonical_report_hash(report)
    return report


def evaluate_capacity_path_b(
    *,
    repo_root: Path,
    symbols: int = DEFAULT_PRODUCTION_SYMBOLS,
    seed: int = DEFAULT_BUDGET_SEED,
    as_of_date: date = DEFAULT_BUDGET_AS_OF_DATE,
) -> tuple[bool, int, dict[str, object]]:
    """Return (within_free_tier, r2_total, full_report) for Path B defaults."""
    inputs = build_path_b_projection_inputs(
        repo_root=repo_root,
        symbols=symbols,
        seed=seed,
        as_of_date=as_of_date,
    )
    breakdown = project_r2_budget_v2(inputs)
    report = build_budget_v2_report(
        inputs=inputs,
        breakdown=breakdown,
        generator_seed=seed,
        as_of_date=as_of_date,
    )
    return bool(report["verdict"]["within_free_tier"]), breakdown.r2_total, report
