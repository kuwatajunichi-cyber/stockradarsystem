from __future__ import annotations

import json
from pathlib import Path

import pytest

from stockradar.jobs import ensure_core_cache as job


def _setup_common(monkeypatch, tmp_path: Path, codes: list[str], statuses: dict[str, str]) -> Path:
    input_path = tmp_path / "input.csv"
    input_path.write_text("code\n1001\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(job, "load_codes_from_csv", lambda _: codes)
    monkeypatch.setattr(job, "get_yf_daily_cache_dir", lambda _: cache_dir)
    monkeypatch.setattr(job, "load_manifest", lambda _: {})
    monkeypatch.setattr(job, "update_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(job, "get_rs_windows", lambda: [31, 63, 126, 252])
    monkeypatch.setattr(job, "get_z_lookback_days", lambda: 60)
    monkeypatch.setattr(job, "get_buffer_days", lambda: 20)
    monkeypatch.setattr(job, "get_yf_batch_size", lambda: 100)
    monkeypatch.setattr(job, "get_yf_sleep_sec_between_batches", lambda: 0)
    monkeypatch.setattr(job, "get_stale_retry_max_passes", lambda: 1)
    monkeypatch.setattr(job, "get_stale_retry_sleep_sec", lambda: 0)
    monkeypatch.setattr(job, "get_stale_allow_continue_max_count", lambda: 9)
    monkeypatch.setattr(job, "ticker_for_code", lambda code: f"{code}.T")
    monkeypatch.setattr(
        job,
        "rebuild_manifest_entry_from_disk",
        lambda code, *_args, **_kwargs: {
            "code": code,
            "symbol": code,
            "requested_days": 272,
            "fetched_bars": 300,
            "status": statuses[code],
            "error": None if statuses[code] == "ok" else "missing_bar_for_run_date",
            "fetched_at": "2026-04-07T00:00:00+00:00",
            "newly_fetched_days": 0,
        },
    )
    monkeypatch.setattr(
        job,
        "ensure_cache_with_incremental_fetch",
        lambda symbol, **_kwargs: {
            "code": symbol,
            "symbol": symbol,
            "requested_days": 272,
            "fetched_bars": 300,
            "status": statuses[symbol],
            "error": None if statuses[symbol] == "ok" else "missing_bar_for_run_date",
            "fetched_at": "2026-04-07T00:00:00+00:00",
            "newly_fetched_days": 0,
        },
    )
    return input_path


def test_stale_under_threshold_continues_and_writes_exclusions(tmp_path: Path, monkeypatch) -> None:
    codes = ["1001", "1002"]
    statuses = {"1001": "ok", "1002": "stale"}
    input_path = _setup_common(monkeypatch, tmp_path, codes, statuses)

    job.main(["--input", str(input_path), "--run-date", "2026-04-07"])

    exclusions_path = tmp_path / "cache" / job.STALE_EXCLUSIONS_FILENAME
    payload = json.loads(exclusions_path.read_text(encoding="utf-8"))
    assert payload["run_date"] == "2026-04-07"
    assert payload["stale_count"] == 1
    assert payload["stale_codes"] == ["1002"]


def test_stale_over_threshold_exits_code2(tmp_path: Path, monkeypatch) -> None:
    codes = [str(1000 + i) for i in range(10)]
    statuses = {c: "stale" for c in codes}
    input_path = _setup_common(monkeypatch, tmp_path, codes, statuses)

    with pytest.raises(SystemExit) as e:
        job.main(["--input", str(input_path), "--run-date", "2026-04-07"])
    assert e.value.code == 2
