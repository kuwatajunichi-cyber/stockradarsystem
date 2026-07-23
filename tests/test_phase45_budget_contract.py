"""Phase 4.5 budget contract (Blocker 4)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from stockradar.storage.phase45_budget import (
    BUDGET_SCHEMA_VERSION,
    R2_WARN_BYTES,
    SUPABASE_WARN_BYTES,
    within_free_tier,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_BENCH = _REPO / "scripts" / "bench" / "phase45_budget_bench.py"


def test_budget_thresholds_match_adr() -> None:
    assert SUPABASE_WARN_BYTES == 350 * 1024 * 1024
    assert R2_WARN_BYTES == 8 * 1024 * 1024 * 1024


def test_ci_scale_within_free_tier(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(_BENCH), "--scale", "ci", "--output", str(out), "--seed", "42"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema_version"] == BUDGET_SCHEMA_VERSION
    assert report["verdict"]["within_free_tier"] is True
    assert report["generator_git_sha"]
    assert any("layer1_r2: 0 (deferred" in note for note in report["verdict"]["notes"])


def test_within_free_tier_rejects_warning_exceed() -> None:
    ok, reasons = within_free_tier(
        supabase_projection_bytes=SUPABASE_WARN_BYTES,
        r2_total_bytes=0,
    )
    assert ok is False
    assert reasons


def test_series_fixture_uses_representative_floats() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("phase45_budget_bench", _BENCH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw_gz = mod.generate_series_gzip_bytes(
        trading_days=50, metrics=5, seed=42, as_of_date=mod.DEFAULT_AS_OF_DATE
    )
    payload = json.loads(__import__("gzip").decompress(raw_gz))
    for vals in payload["series"].values():
        assert len(vals) == 50
        diffs = {round(vals[i + 1] - vals[i], 6) for i in range(len(vals) - 1)}
        assert len(diffs) > 1


def test_daily_snapshots_measured_per_trade_date() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("phase45_budget_bench", _BENCH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    one_day, _ = mod.generate_daily_parquet_bytes(
        symbols=10, metrics=5, trading_days=1, seed=7, as_of_date=mod.DEFAULT_AS_OF_DATE
    )
    three_days, _ = mod.generate_daily_parquet_bytes(
        symbols=10, metrics=5, trading_days=3, seed=7, as_of_date=mod.DEFAULT_AS_OF_DATE
    )
    assert three_days > one_day
    assert three_days >= one_day * 3


def test_daily_parquet_uses_unique_temp_paths() -> None:
    source = _BENCH.read_text(encoding="utf-8")
    assert "_tmp_bench.parquet" not in source
    assert "NamedTemporaryFile" in source
    assert "date.today()" not in source
    assert "DEFAULT_AS_OF_DATE" in source


def test_full_scale_fails_without_layer1_bytes() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("phase45_budget_bench", _BENCH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.build_report(
        scale="full",
        symbols=2,
        metrics=2,
        trading_days=2,
        seed=1,
        layer1_r2_bytes=0,
    )
    assert report["verdict"]["within_free_tier"] is False
    assert any("layer1_r2: missing" in note for note in report["verdict"]["notes"])
