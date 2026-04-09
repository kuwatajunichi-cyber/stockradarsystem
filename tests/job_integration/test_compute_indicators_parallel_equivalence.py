from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import stockradar.jobs.compute_indicators_for_core as job


pytestmark = pytest.mark.job_integration


def _write_cache(path: Path, close: list[float], volume: list[float], idx: pd.DatetimeIndex) -> None:
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )
    df.to_csv(path, encoding="utf-8-sig")


def _run_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workers: int | None) -> pd.DataFrame:
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_csv = tmp_path / "core.csv"
    input_csv.write_text("code,name\n1001,AAA\n1002,BBB\n", encoding="utf-8")
    daily = tmp_path / "yf_daily"
    index = tmp_path / "yf_index"
    out = tmp_path / "indicators"
    daily.mkdir(parents=True, exist_ok=True)
    index.mkdir(parents=True, exist_ok=True)

    idx = pd.to_datetime(["2026-04-04", "2026-04-07", "2026-04-08"], utc=True)
    _write_cache(daily / "1001.csv", [100.0, 101.0, 102.0], [1000.0, 1100.0, 1200.0], idx)
    _write_cache(daily / "1002.csv", [200.0, 201.0, 202.0], [1000.0, 1100.0, 1200.0], idx)
    pd.DataFrame({"Close": [300.0, 301.0, 302.0]}, index=idx).to_csv(index / "topix.csv", encoding="utf-8-sig")
    pd.DataFrame({"Close": [400.0, 401.0, 402.0]}, index=idx).to_csv(index / "nikkei.csv", encoding="utf-8-sig")

    monkeypatch.setattr(job, "get_yf_daily_cache_dir", lambda _base: daily)
    monkeypatch.setattr(job, "get_yf_index_cache_dir", lambda _base: index)
    monkeypatch.setattr(job, "get_indicators_daily_dir", lambda _base: out)
    monkeypatch.setattr(job, "get_z_lookback_days", lambda: 2)
    monkeypatch.setattr(job, "get_rs_windows", lambda: [1, 2])
    monkeypatch.setattr(job, "get_rs_benchmark", lambda: "BOTH")
    monkeypatch.setattr(job, "get_indicators_max_workers", lambda: workers)

    job.main(["--input", str(input_csv), "--run-date", "2026-04-08"])
    return pd.read_csv(out / "indicators_20260408.csv")


def test_parallel_workers_2_and_4_match_serial_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serial = _run_once(tmp_path / "serial", monkeypatch, 1).sort_values("code").reset_index(drop=True)
    workers2 = _run_once(tmp_path / "w2", monkeypatch, 2).sort_values("code").reset_index(drop=True)
    workers4 = _run_once(tmp_path / "w4", monkeypatch, 4).sort_values("code").reset_index(drop=True)

    pd.testing.assert_frame_equal(serial, workers2, check_dtype=False, check_like=False)
    pd.testing.assert_frame_equal(serial, workers4, check_dtype=False, check_like=False)
