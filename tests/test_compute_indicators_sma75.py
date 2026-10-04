"""Unit: compute_indicators emits rs_sma75_* from sma75_rs pure."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import stockradar.jobs.compute_indicators_for_core as job
from stockradar.prototype_web_ui_asof.sma75_rs import compute_rs_sma75_from_closes

pytestmark = pytest.mark.unit


def test_compute_one_code_includes_sma75_matching_pure(tmp_path, monkeypatch) -> None:
    idx = pd.to_datetime(pd.bdate_range("2025-01-02", periods=120, freq="C"))
    stock = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": [100.0 + i * 0.2 for i in range(120)],
            "Volume": 1000.0,
        },
        index=idx,
    )
    bench = pd.DataFrame(
        {"Close": [300.0 + i * 0.05 for i in range(120)]},
        index=idx,
    )
    daily = tmp_path / "yf_daily"
    daily.mkdir()
    stock.to_csv(daily / "7203.csv")
    run = idx[-1].date()
    assert isinstance(run, date)
    job._WORKER_CTX = {
        "run_date": run,
        "daily_cache_dir": str(daily),
        "z_lookback_days": 60,
        "rs_windows": [31, 63],
        "benchmarks": {"topix": bench},
        "compute_candle": False,
    }
    monkeypatch.setattr(job, "load_cache", lambda path: pd.read_csv(path, index_col=0, parse_dates=True))
    out = job._compute_one_code(("7203", "Toyota"))
    assert out["status"] == "ok"
    got = out["row"]["rs_sma75_topix"]
    expected = compute_rs_sma75_from_closes(stock["Close"], bench["Close"], run)
    assert got == pytest.approx(expected)
    assert got is not None
