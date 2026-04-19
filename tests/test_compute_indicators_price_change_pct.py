"""run_date 当日終値に基づく price_change_pct の契約テスト。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import stockradar.jobs.compute_indicators_for_core as job

pytestmark = pytest.mark.job_integration


def test_price_change_pct_none_when_latest_close_na(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """当日バー終値が NaN のとき、古いバー同士で騰落率を出さず欠損とする。"""
    input_csv = tmp_path / "core.csv"
    input_csv.write_text("code,name\n1001,AAA\n", encoding="utf-8")
    daily = tmp_path / "yf_daily"
    index = tmp_path / "yf_index"
    out = tmp_path / "indicators"
    daily.mkdir(parents=True, exist_ok=True)
    index.mkdir(parents=True, exist_ok=True)

    idx = pd.to_datetime(["2026-04-04", "2026-04-07", "2026-04-08"], utc=True)
    pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [100.0, 101.0, 102.0],
            "Low": [100.0, 101.0, 102.0],
            "Close": [100.0, 101.0, np.nan],
            "Volume": [1000.0, 1100.0, 1200.0],
        },
        index=idx,
    ).to_csv(daily / "1001.csv", encoding="utf-8-sig")
    pd.DataFrame({"Close": [300.0, 301.0, 302.0]}, index=idx).to_csv(index / "topix.csv", encoding="utf-8-sig")
    pd.DataFrame({"Close": [400.0, 401.0, 402.0]}, index=idx).to_csv(index / "nikkei.csv", encoding="utf-8-sig")

    monkeypatch.setattr(job, "get_yf_daily_cache_dir", lambda _base: daily)
    monkeypatch.setattr(job, "get_yf_index_cache_dir", lambda _base: index)
    monkeypatch.setattr(job, "get_indicators_daily_dir", lambda _base: out)
    monkeypatch.setattr(job, "get_z_lookback_days", lambda: 2)
    monkeypatch.setattr(job, "get_rs_windows", lambda: [1, 2])
    monkeypatch.setattr(job, "get_rs_benchmark", lambda: "BOTH")
    monkeypatch.setattr(job, "get_indicators_max_workers", lambda: 1)

    job.main(["--input", str(input_csv), "--run-date", "2026-04-08"])
    df = pd.read_csv(out / "indicators_20260408.csv")
    assert len(df) == 1
    assert pd.isna(df["price_change_pct"].iloc[0])


def test_price_change_pct_when_latest_close_valid(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """当日終値・前日終値が有効なときは百分率騰落率が入る。"""
    input_csv = tmp_path / "core.csv"
    input_csv.write_text("code,name\n1001,AAA\n", encoding="utf-8")
    daily = tmp_path / "yf_daily"
    index = tmp_path / "yf_index"
    out = tmp_path / "indicators"
    daily.mkdir(parents=True, exist_ok=True)
    index.mkdir(parents=True, exist_ok=True)

    idx = pd.to_datetime(["2026-04-04", "2026-04-07", "2026-04-08"], utc=True)
    pd.DataFrame(
        {
            "Open": [100.0, 100.0, 110.0],
            "High": [100.0, 100.0, 110.0],
            "Low": [100.0, 100.0, 110.0],
            "Close": [100.0, 100.0, 110.0],
            "Volume": [1000.0, 1000.0, 1000.0],
        },
        index=idx,
    ).to_csv(daily / "1001.csv", encoding="utf-8-sig")
    pd.DataFrame({"Close": [300.0, 301.0, 302.0]}, index=idx).to_csv(index / "topix.csv", encoding="utf-8-sig")
    pd.DataFrame({"Close": [400.0, 401.0, 402.0]}, index=idx).to_csv(index / "nikkei.csv", encoding="utf-8-sig")

    monkeypatch.setattr(job, "get_yf_daily_cache_dir", lambda _base: daily)
    monkeypatch.setattr(job, "get_yf_index_cache_dir", lambda _base: index)
    monkeypatch.setattr(job, "get_indicators_daily_dir", lambda _base: out)
    monkeypatch.setattr(job, "get_z_lookback_days", lambda: 2)
    monkeypatch.setattr(job, "get_rs_windows", lambda: [1, 2])
    monkeypatch.setattr(job, "get_rs_benchmark", lambda: "BOTH")
    monkeypatch.setattr(job, "get_indicators_max_workers", lambda: 1)

    job.main(["--input", str(input_csv), "--run-date", "2026-04-08"])
    df = pd.read_csv(out / "indicators_20260408.csv")
    assert df["price_change_pct"].iloc[0] == pytest.approx(10.0)
