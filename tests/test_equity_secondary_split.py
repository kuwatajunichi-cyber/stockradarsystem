from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stockradar.universe.equity_secondary import split_equity_domestic_secondary


def _write_manifest_line(path: Path, entry: dict) -> None:
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")


def test_stale_with_sufficient_bars_not_in_ipo(tmp_path: Path) -> None:
    """stale だが本数十分なら二次分割では IPO に寄せない（流動性判定へ）。"""
    code = "9999"
    cache_dir = tmp_path / "yf"
    cache_dir.mkdir()
    idx = pd.bdate_range("2026-01-01", periods=50)
    df = pd.DataFrame(
        {"Close": [100.0] * 50, "Volume": [10_000.0] * 50},
        index=idx,
    )
    df.to_csv(cache_dir / f"{code}.csv", encoding="utf-8-sig")

    manifest_path = tmp_path / "_manifest_universe.jsonl"
    _write_manifest_line(
        manifest_path,
        {
            "code": code,
            "requested_days": 50,
            "fetched_bars": 50,
            "status": "stale",
            "error": "missing_bar_for_run_date",
            "fetched_at": "2026-04-02T00:00:00+00:00",
        },
    )

    result = split_equity_domestic_secondary(
        codes=[code],
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        ipo_lookback_days=40,
        liq_lookback_days=20,
        liq_min_median_turnover_yen=1.0,
    )
    assert code not in result.ipo
    assert code in result.core
    assert result.summary.get("n_stale_run_date") == 1


def test_manifest_symbol_only_line_loadable(tmp_path: Path) -> None:
    """JSONL が symbol のみでも code として読める。"""
    code = "8888"
    cache_dir = tmp_path / "yf"
    cache_dir.mkdir()
    idx = pd.bdate_range("2026-01-01", periods=50)
    df = pd.DataFrame(
        {"Close": [50.0] * 50, "Volume": [20_000.0] * 50},
        index=idx,
    )
    df.to_csv(cache_dir / f"{code}.csv", encoding="utf-8-sig")

    manifest_path = tmp_path / "m.jsonl"
    _write_manifest_line(
        manifest_path,
        {
            "symbol": code,
            "requested_days": 50,
            "fetched_bars": 50,
            "status": "ok",
            "error": None,
            "fetched_at": "x",
        },
    )

    result = split_equity_domestic_secondary(
        codes=[code],
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        ipo_lookback_days=40,
        liq_lookback_days=20,
        liq_min_median_turnover_yen=1.0,
    )
    assert code in result.core
    assert result.summary.get("n_stale_run_date") == 0
