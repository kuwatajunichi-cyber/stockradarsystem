"""Facade. The implementation lives in stockradar.indicators.sma75_rs."""
from __future__ import annotations

from stockradar.indicators.sma75_rs import (
    compute_close_rs75_from_closes,
    compute_rs_sma75_from_closes,
    sma_series,
)

__all__ = [
    "compute_close_rs75_from_closes",
    "compute_rs_sma75_from_closes",
    "sma_series",
]
