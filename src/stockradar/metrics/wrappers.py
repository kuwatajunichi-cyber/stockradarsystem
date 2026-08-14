"""Thin wrappers delegating to existing indicators with explicit version params."""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockradar.indicators.risk_adjusted import (
    compute_beta_adjusted_rs_from_merged,
    compute_information_ratio_from_merged,
)
from stockradar.indicators.rs import (
    compute_rs_acceleration_from_merged,
    compute_rs_acceleration_zscore_from_merged,
    compute_rs_from_merged,
)
from stockradar.indicators.zscore import (
    compute_turnover_ma_ratio_from_prepared,
    compute_zscore_turnover_from_prepared,
)
from stockradar.metrics.perfect_order import compute_perfect_order_days


def compute_z_turnover(
    stock_df: pd.DataFrame,
    *,
    z_lookback_days: int,
    run_date: date,
    anchor_ctx=None,
) -> float | None:
    series = compute_zscore_turnover_from_prepared(
        stock_df, z_lookback_days, run_date, anchor_ctx=anchor_ctx
    )
    if series.empty:
        return None
    val = series.iloc[0]
    return None if pd.isna(val) else float(val)


def compute_turnover_ma_ratio(
    stock_df: pd.DataFrame,
    *,
    z_lookback_days: int,
    run_date: date,
    anchor_ctx=None,
) -> float | None:
    series = compute_turnover_ma_ratio_from_prepared(
        stock_df, z_lookback_days, run_date, anchor_ctx=anchor_ctx
    )
    if series.empty:
        return None
    val = series.iloc[0]
    return None if pd.isna(val) else float(val)


def compute_rs_values(
    merged: pd.DataFrame,
    *,
    rs_windows: list[int],
    run_date: date,
    anchor_ctx=None,
    stock_asof=None,
    bench_asof=None,
) -> dict[str, float | None]:
    df = compute_rs_from_merged(
        merged,
        rs_windows,
        run_date,
        anchor_ctx=anchor_ctx,
        stock_asof=stock_asof,
        bench_asof=bench_asof,
    )
    if df.empty:
        return {f"rs{T}": None for T in rs_windows}
    row = df.iloc[0]
    return {f"rs{T}": (None if pd.isna(row[f"rs{T}"]) else float(row[f"rs{T}"])) for T in rs_windows}


__all__ = [
    "compute_beta_adjusted_rs_from_merged",
    "compute_information_ratio_from_merged",
    "compute_perfect_order_days",
    "compute_rs_acceleration_from_merged",
    "compute_rs_acceleration_zscore_from_merged",
    "compute_rs_from_merged",
    "compute_rs_values",
    "compute_turnover_ma_ratio",
    "compute_z_turnover",
]
