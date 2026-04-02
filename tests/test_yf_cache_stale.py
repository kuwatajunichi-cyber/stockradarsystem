from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.utils.yf_cache import (
    ERROR_INSUFFICIENT_BARS,
    ERROR_MISSING_BAR_FOR_RUN_DATE,
    classify_cache_row_status,
    ensure_cache_with_incremental_fetch,
)


def test_classify_insufficient_vs_stale() -> None:
    d = date(2026, 4, 2)
    assert classify_cache_row_status(5, 10, date(2026, 4, 1), d) == (
        "insufficient",
        ERROR_INSUFFICIENT_BARS,
    )
    assert classify_cache_row_status(10, 10, date(2026, 4, 1), d) == (
        "stale",
        ERROR_MISSING_BAR_FOR_RUN_DATE,
    )
    assert classify_cache_row_status(10, 10, date(2026, 4, 2), d) == ("ok", None)
    assert classify_cache_row_status(10, 10, date(2026, 4, 2), None) == ("ok", None)


def test_manifest_ok_but_disk_last_date_before_run_date_is_stale(
    tmp_path: Path, monkeypatch
) -> None:
    """manifest が ok でも CSV 実体を照合し、取得しても run_date に届かなければ stale。"""

    symbol = "7203"
    run_date = date(2026, 4, 2)
    cache_path = tmp_path / f"{symbol}.csv"
    idx = pd.to_datetime(["2026-03-30", "2026-03-31", "2026-04-01"])
    df = pd.DataFrame(
        {
            "Open": [1.0, 1.0, 1.0],
            "High": [1.0, 1.0, 1.0],
            "Low": [1.0, 1.0, 1.0],
            "Close": [1.0, 1.0, 1.0],
            "Volume": [100.0, 100.0, 100.0],
        },
        index=idx,
    )
    df.to_csv(cache_path, encoding="utf-8-sig")

    idx_api = pd.to_datetime(
        ["2026-03-28", "2026-03-29", "2026-03-30", "2026-03-31", "2026-04-01"]
    )
    api_df = pd.DataFrame(
        {
            "Open": [1.0] * 5,
            "High": [1.0] * 5,
            "Low": [1.0] * 5,
            "Close": [1.0] * 5,
            "Volume": [100.0] * 5,
        },
        index=idx_api,
    )

    def _fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        return api_df

    monkeypatch.setattr("stockradar.utils.yf_cache.fetch_yf_data", _fake_fetch)

    manifest = {
        symbol: {
            "code": symbol,
            "symbol": symbol,
            "requested_days": 3,
            "fetched_bars": 3,
            "status": "ok",
            "error": None,
            "fetched_at": "2026-04-02T00:00:00+00:00",
        }
    }
    ent = ensure_cache_with_incremental_fetch(
        symbol=symbol,
        ticker=f"{symbol}.T",
        cache_path=cache_path,
        manifest=manifest,
        required_days=3,
        run_date=run_date,
        force=False,
    )
    assert ent["status"] == "stale"
    assert ent.get("error") == ERROR_MISSING_BAR_FOR_RUN_DATE
    assert ent.get("code") == symbol
    assert ent.get("symbol") == symbol
