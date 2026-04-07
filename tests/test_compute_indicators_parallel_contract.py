from __future__ import annotations

import concurrent.futures
from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.jobs.compute_indicators_for_core import _compute_one_code, _init_worker


def test_compute_one_code_parallel_matches_serial(tmp_path: Path) -> None:
    idx = pd.to_datetime(["2026-04-04", "2026-04-07", "2026-04-08"])
    stock_df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.0, 101.0, 102.0],
            "Volume": [1000.0, 1200.0, 1300.0],
        },
        index=idx,
    )
    cache_dir = tmp_path / "yf_daily"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stock_df.to_csv(cache_dir / "1001.csv", encoding="utf-8-sig")

    bench_df = pd.DataFrame({"Close": [200.0, 202.0, 203.0]}, index=idx)
    ctx = {
        "run_date": date(2026, 4, 8),
        "daily_cache_dir": str(cache_dir),
        "z_lookback_days": 21,
        "rs_windows": [1, 2],
        "benchmarks": {"topix": bench_df},
        "compute_candle": False,
    }
    _init_worker(ctx)
    serial = _compute_one_code(("1001", "AAA"))

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=1,
        initializer=_init_worker,
        initargs=(ctx,),
    ) as ex:
        parallel = list(ex.map(_compute_one_code, [("1001", "AAA")]))[0]

    assert serial["status"] == "ok"
    assert parallel["status"] == "ok"
    assert serial["row"]["code"] == parallel["row"]["code"] == "1001"
    assert serial["row"]["date"] == parallel["row"]["date"] == "2026-04-08"
