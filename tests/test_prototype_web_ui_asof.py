"""Unit tests for localhost Web UI as-of prototype (fixtures only)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from stockradar.prototype_web_ui_asof.axis import require_index_asof_bar, xtks_axis_dates
from stockradar.prototype_web_ui_asof.display_scale import y_z_from_z
from stockradar.prototype_web_ui_asof.free_preview import free_preview_keep_mask
from stockradar.prototype_web_ui_asof.freeze_core import FreezePaths, freeze_asof, _to_session_calendar_index
from stockradar.prototype_web_ui_asof.isolation import (
    assert_gate_track_d_still_open,
    scan_source_for_forbidden_imports,
    validate_bind_host,
    validate_readme_markers,
)
from stockradar.prototype_web_ui_asof.sma75_rs import (
    compute_close_rs75_from_closes,
    compute_rs_sma75_from_closes,
)
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "prototype_web_ui_asof"
AS_OF = date(2024, 12, 30)


@pytest.fixture(scope="module")
def fixtures_ready() -> Path:
    builder = FIX / "build_fixtures.py"
    subprocess.check_call([sys.executable, str(builder)], cwd=str(REPO))
    return FIX


@pytest.fixture(scope="module")
def frozen_db(fixtures_ready: Path, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("proto") / "fixture.sqlite"
    paths = FreezePaths(
        csv_path=fixtures_ready / "indicators_event_enriched_fixture.csv",
        daily_cache_dir=fixtures_ready / "yf_daily",
        index_cache_dir=fixtures_ready / "yf_index",
        out_sqlite=out,
    )
    meta = freeze_asof(paths, as_of=AS_OF, reconcile_code="7203")
    assert meta["n_rows"] >= 1
    assert meta["axis_len"] == 60
    return out


@pytest.mark.unit
def test_readme_p_iso_markers() -> None:
    text = (REPO / "prototypes" / "web-ui-asof" / "README.md").read_text(encoding="utf-8")
    assert validate_readme_markers(text) == []


@pytest.mark.unit
def test_freeze_source_has_no_forbidden_imports() -> None:
    pkg = REPO / "src" / "stockradar" / "prototype_web_ui_asof"
    # isolation module mentions forbidden tokens in strings; scan freeze_core only
    core = (pkg / "freeze_core.py").read_text(encoding="utf-8")
    assert scan_source_for_forbidden_imports(core) == []


@pytest.mark.unit
def test_gate_track_d_still_open() -> None:
    gate = yaml.safe_load(
        (REPO / "docs" / "operations" / "phase5_gate_status.yaml").read_text(encoding="utf-8")
    )
    assert assert_gate_track_d_still_open(gate) == []


@pytest.mark.unit
def test_bind_host_127_only() -> None:
    validate_bind_host("127.0.0.1")
    for bad in ("", "0.0.0.0", "::", "localhost"):
        with pytest.raises(ValueError):
            validate_bind_host(bad)


@pytest.mark.unit
def test_axis_keeps_missing_symbol_day(fixtures_ready: Path, frozen_db: Path) -> None:
    axis = xtks_axis_dates(AS_OF, n=60)
    assert len(axis) == 60
    with sqlite3.connect(frozen_db) as conn:
        meta = conn.execute("SELECT axis_dates_json FROM meta").fetchone()[0]
        dates = json.loads(meta)
        assert dates == [d.isoformat() for d in axis]
        row = conn.execute("SELECT metrics_json FROM series WHERE code='9984'").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        z = payload["values"]["z_turnover_60"]
        assert len(z) == 60
        assert any(v is None for v in z)


@pytest.mark.unit
def test_freeze_fails_when_index_missing_asof(fixtures_ready: Path, tmp_path: Path) -> None:
    # copy index without as-of bar
    import shutil

    idx = tmp_path / "yf_index"
    shutil.copytree(fixtures_ready / "yf_index", idx)
    topix = pd.read_csv(idx / "topix.csv", index_col=0, parse_dates=True)
    topix = topix[topix.index.date < AS_OF]
    topix.to_csv(idx / "topix.csv")
    paths = FreezePaths(
        csv_path=fixtures_ready / "indicators_event_enriched_fixture.csv",
        daily_cache_dir=fixtures_ready / "yf_daily",
        index_cache_dir=idx,
        out_sqlite=tmp_path / "x.sqlite",
    )
    with pytest.raises(ValueError, match="missing as-of"):
        freeze_asof(paths, as_of=AS_OF)


@pytest.mark.unit
def test_reconcile_last_bar_matches_csv(frozen_db: Path, fixtures_ready: Path) -> None:
    csv = pd.read_csv(fixtures_ready / "indicators_event_enriched_fixture.csv")
    row = csv[csv["code"].astype(str).str.zfill(4) == "7203"].iloc[0]
    with sqlite3.connect(frozen_db) as conn:
        payload = json.loads(
            conn.execute("SELECT payload_json FROM rows WHERE code='7203'").fetchone()[0]
        )
        series = json.loads(
            conn.execute("SELECT metrics_json FROM series WHERE code='7203'").fetchone()[0]
        )
    assert abs(float(payload["z_turnover_60"]) - float(row["z_turnover_60"])) < 1e-9
    assert abs(float(payload["rs31_topix"]) - float(row["rs31_topix"])) < 1e-9
    assert "rs_sma75_topix" in payload
    # table last bar and series last bar must be identical (no dual-source drift)
    assert series["values"]["z_turnover_60"][-1] == payload["z_turnover_60"]
    assert series["values"]["rs31_topix"][-1] == payload["rs31_topix"]
    assert series["values"]["rs_sma75_topix"][-1] == payload["rs_sma75_topix"]
    assert isinstance(payload.get("price_text"), str) and payload["price_text"]


@pytest.mark.unit
def test_sma75_rs_differs_from_close_rs75(fixtures_ready: Path) -> None:
    stock = pd.read_csv(fixtures_ready / "yf_daily" / "7203.csv", index_col=0, parse_dates=True)
    topix = pd.read_csv(fixtures_ready / "yf_index" / "topix.csv", index_col=0, parse_dates=True)
    a = compute_rs_sma75_from_closes(stock["Close"], topix["Close"], AS_OF)
    b = compute_close_rs75_from_closes(stock["Close"], topix["Close"], AS_OF)
    assert a is not None and b is not None
    assert abs(a - b) > 1e-12


@pytest.mark.unit
def test_display_scale_no_clamp() -> None:
    assert y_z_from_z(10.0) == 2.0
    assert y_z_from_z(-15.0) == -3.0
    assert y_z_from_z(None) is None


@pytest.mark.unit
def test_free_preview_ties_and_nan() -> None:
    z = [1.0, 1.0, 0.9, None, float("nan"), 0.5]
    # top_n=2 => threshold 1.0, both ties kept
    mask = free_preview_keep_mask(z, top_n=2)
    assert mask == [True, True, False, False, False, False]
    # fewer than top_n finite => keep all finite
    mask2 = free_preview_keep_mask([None, 1.0, 2.0], top_n=20)
    assert mask2 == [False, True, True]


@pytest.mark.unit
def test_session_calendar_index_keeps_tokyo_friday() -> None:
    # yfinance JP bar at midnight +09 must not shift back to Thursday.
    idx = pd.DatetimeIndex(
        [
            "2026-05-21T00:00:00+09:00",
            "2026-05-22T00:00:00+09:00",
            "2026-05-25T00:00:00+09:00",
        ]
    )
    out = _to_session_calendar_index(idx)
    assert [ts.date().isoformat() for ts in out] == [
        "2026-05-21",
        "2026-05-22",
        "2026-05-25",
    ]


@pytest.mark.unit
def test_require_index_asof_bar() -> None:
    require_index_asof_bar({AS_OF}, AS_OF, label="topix")
    with pytest.raises(ValueError):
        require_index_asof_bar(set(), AS_OF, label="topix")


@pytest.mark.unit
def test_discover_asof_catalog(tmp_path: Path) -> None:
    import importlib.util

    serve_path = REPO / "scripts" / "prototype_web_ui_asof" / "serve.py"
    spec = importlib.util.spec_from_file_location("proto_serve", serve_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "2026-08-13.sqlite").write_bytes(b"x")
    (tmp_path / "2026-08-17.sqlite").write_bytes(b"yy")
    (tmp_path / "notes.txt").write_text("no", encoding="utf-8")
    (tmp_path / "2026-01-01.sqlite").write_bytes(b"")  # size 0 ignored
    catalog = mod.discover_asof_catalog(tmp_path)
    assert list(catalog.keys()) == ["2026-08-13", "2026-08-17"]

