"""rebuild_manifest_entry_from_disk：ディスク真実で manifest を再構築する。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.utils.yf_cache import (
    ERROR_INSUFFICIENT_BARS,
    ERROR_MISSING_BAR_FOR_RUN_DATE,
    rebuild_manifest_entry_from_disk,
)


def test_reconcile_ok_csv_matches_run_date(tmp_path: Path) -> None:
    p = tmp_path / "7203.csv"
    idx = pd.to_datetime(["2026-04-01", "2026-04-02"])
    df = pd.DataFrame(
        {
            "Open": [1.0, 1.0],
            "High": [1.0, 1.0],
            "Low": [1.0, 1.0],
            "Close": [1.0, 1.0],
            "Volume": [100.0, 100.0],
        },
        index=idx,
    )
    df.to_csv(p, encoding="utf-8-sig")
    ent = rebuild_manifest_entry_from_disk(
        "7203",
        p,
        requested_days=2,
        run_date=date(2026, 4, 2),
        fetched_at="t",
    )
    assert ent["status"] == "ok"
    assert ent["fetched_bars"] == 2
    assert ent.get("error") is None


def test_reconcile_stale_when_disk_ends_before_run_date(tmp_path: Path) -> None:
    p = tmp_path / "7203.csv"
    idx = pd.to_datetime(["2026-03-31", "2026-04-01"])
    df = pd.DataFrame(
        {
            "Open": [1.0, 1.0],
            "High": [1.0, 1.0],
            "Low": [1.0, 1.0],
            "Close": [1.0, 1.0],
            "Volume": [100.0, 100.0],
        },
        index=idx,
    )
    df.to_csv(p, encoding="utf-8-sig")
    ent = rebuild_manifest_entry_from_disk(
        "7203",
        p,
        requested_days=2,
        run_date=date(2026, 4, 2),
        fetched_at="t",
    )
    assert ent["status"] == "stale"
    assert ent.get("error") == ERROR_MISSING_BAR_FOR_RUN_DATE


def test_reconcile_overwrites_fake_ok_in_memory_scenario(tmp_path: Path) -> None:
    """manifest が誤って ok でも CSV が前日までなら stale に直る。"""
    p = tmp_path / "9999.csv"
    idx = pd.date_range("2026-03-28", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "Open": [1.0] * 5,
            "High": [1.0] * 5,
            "Low": [1.0] * 5,
            "Close": [1.0] * 5,
            "Volume": [100.0] * 5,
        },
        index=idx,
    )
    df.to_csv(p, encoding="utf-8-sig")
    ent = rebuild_manifest_entry_from_disk(
        "9999",
        p,
        requested_days=5,
        run_date=date(2026, 4, 10),
        fetched_at="t",
    )
    assert ent["status"] == "stale"


def test_reconcile_missing_file_insufficient(tmp_path: Path) -> None:
    p = tmp_path / "nope.csv"
    ent = rebuild_manifest_entry_from_disk(
        "1111",
        p,
        requested_days=3,
        run_date=date(2026, 4, 1),
        fetched_at="t",
    )
    assert ent["status"] == "insufficient"
    assert ent.get("error") == ERROR_INSUFFICIENT_BARS
