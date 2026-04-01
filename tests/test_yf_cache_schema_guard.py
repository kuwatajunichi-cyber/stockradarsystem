from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.utils.yf_cache import ensure_cache_with_incremental_fetch


def _make_df(index_dates: list[str], columns: list[str]) -> pd.DataFrame:
    data = {col: [float(i + 1) for i in range(len(index_dates))] for col in columns}
    df = pd.DataFrame(data, index=pd.to_datetime(index_dates))
    return df


def test_schema_mismatch_forces_full_fetch_even_if_latest_date_is_enough(
    tmp_path: Path, monkeypatch
) -> None:
    symbol = "7203"
    run_date = date(2026, 3, 31)
    cache_path = tmp_path / f"{symbol}.csv"

    # 旧スキーマ（Close, Volumeのみ）
    old_df = _make_df(["2026-03-30", "2026-03-31"], ["Close", "Volume"])
    old_df.to_csv(cache_path, encoding="utf-8-sig")

    fetched_df = _make_df(
        ["2026-03-30", "2026-03-31"],
        ["Open", "High", "Low", "Close", "Volume"],
    )
    calls: list[tuple[str, int, date | None, date | None]] = []

    def _fake_fetch_yf_data(
        ticker: str,
        required_days: int,
        run_date_arg: date | None = None,
        start_date: date | None = None,
        retry_max: int | None = None,
        backoff_sec: list[int] | None = None,
    ) -> pd.DataFrame:
        calls.append((ticker, required_days, run_date_arg, start_date))
        return fetched_df

    monkeypatch.setattr("stockradar.utils.yf_cache.fetch_yf_data", _fake_fetch_yf_data)

    manifest = {
        symbol: {
            "symbol": symbol,
            "requested_days": 2,
            "fetched_bars": 2,
            "status": "ok",
            "error": None,
            "fetched_at": "2026-03-31T06:00:00+00:00",
        }
    }
    ent = ensure_cache_with_incremental_fetch(
        symbol=symbol,
        ticker=f"{symbol}.T",
        cache_path=cache_path,
        manifest=manifest,
        required_days=2,
        run_date=run_date,
        force=False,
    )

    assert len(calls) == 1
    # 早期returnされず、差分ではなくフル取得で自己修復する
    assert calls[0][3] is None
    assert ent["status"] == "ok"
    assert str(ent.get("error", "")).startswith("schema_mismatch_missing_ohlcv:")
    reloaded = pd.read_csv(cache_path, encoding="utf-8-sig", index_col=0)
    assert {"Open", "High", "Low", "Close", "Volume"}.issubset(set(reloaded.columns))


def test_valid_schema_and_latest_cache_skips_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    symbol = "6758"
    run_date = date(2026, 3, 31)
    cache_path = tmp_path / f"{symbol}.csv"
    valid_df = _make_df(
        ["2026-03-30", "2026-03-31"],
        ["Open", "High", "Low", "Close", "Volume"],
    )
    valid_df.to_csv(cache_path, encoding="utf-8-sig")

    def _unexpected_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("valid schema + latest date ではfetchしない想定")

    monkeypatch.setattr("stockradar.utils.yf_cache.fetch_yf_data", _unexpected_fetch)

    manifest = {
        symbol: {
            "symbol": symbol,
            "requested_days": 2,
            "fetched_bars": 2,
            "status": "ok",
            "error": None,
            "fetched_at": "2026-03-31T06:00:00+00:00",
        }
    }
    ent = ensure_cache_with_incremental_fetch(
        symbol=symbol,
        ticker=f"{symbol}.T",
        cache_path=cache_path,
        manifest=manifest,
        required_days=2,
        run_date=run_date,
        force=False,
    )

    assert ent["status"] == "ok"
    assert ent["newly_fetched_days"] == 0
    assert ent.get("error") is None
