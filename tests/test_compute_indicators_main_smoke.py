from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import stockradar.jobs.compute_indicators_for_core as job


def test_compute_indicators_main_reaches_worker_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    valid run-date 経路で main() 初期化を通すスモーク。
    os.cpu_count() 等の初期化欠落を検知する。
    """
    input_path = tmp_path / "core.csv"
    input_path.write_text("code,name\n1001,AAA\n", encoding="utf-8")

    monkeypatch.setattr(job, "_load_codes_with_names", lambda _p: pd.DataFrame([{"code": "1001", "name": "AAA"}]))
    monkeypatch.setattr(job, "get_yf_daily_cache_dir", lambda _base: tmp_path / "yf_daily")
    monkeypatch.setattr(job, "get_yf_index_cache_dir", lambda _base: tmp_path / "yf_index")
    monkeypatch.setattr(job, "get_indicators_daily_dir", lambda _base: tmp_path / "indicators")
    monkeypatch.setattr(job, "get_z_lookback_days", lambda: 60)
    monkeypatch.setattr(job, "get_rs_windows", lambda: [31, 63, 126, 252])
    monkeypatch.setattr(job, "get_rs_benchmark", lambda: "BOTH")
    monkeypatch.setattr(job, "get_indicators_max_workers", lambda: None)
    monkeypatch.setattr(job, "load_cache", lambda _p: None)

    with pytest.raises(SystemExit) as e:
        job.main(["--input", str(input_path), "--run-date", "2026-04-09"])
    assert e.value.code == 1
