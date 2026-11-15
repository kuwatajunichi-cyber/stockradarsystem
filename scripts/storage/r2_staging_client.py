"""Compatibility re-export. The adapter lives in stockradar.storage.r2_staging."""
from __future__ import annotations

from stockradar.storage.r2_staging import (
    R2StagingAdapter,
    R2StagingPort,
    get_json,
    put_json,
)

__all__ = [
    "R2StagingAdapter",
    "R2StagingPort",
    "get_json",
    "put_json",
]
