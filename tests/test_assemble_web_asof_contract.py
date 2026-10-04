"""Contract: freeze sqlite projects to web_asof_bundle_v1 payloads."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from stockradar.jobs.assemble_web_asof import (
    AssembleWebAsofError,
    catalog_from_registry_row,
    payloads_from_freeze_sqlite,
    write_payload_files,
    write_universe_csv_from_ohlc_zip,
)
from stockradar.storage.web_asof_bundle import AXIS_LEN, SCHEMA_ID, validate_web_asof_bundle

pytestmark = pytest.mark.unit

_FP = "b" * 64
_SET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _axis() -> list[str]:
    days = [f"2026-07-{i:02d}" for i in range(1, 32)] + [f"2026-08-{i:02d}" for i in range(1, 32)]
    return days[:AXIS_LEN]


def _write_sqlite(path: Path, *, sma_topix: float | None, sma_nikkei: float | None) -> None:
    axis = _axis()
    as_of = axis[-1]
    n = AXIS_LEN
    values = {
        "z_turnover_60": [0.1] * n,
        "rs_acceleration_topix": [0.2] * n,
        "rs_acceleration_nikkei": [0.3] * n,
        "rs_acceleration_zscore_topix": [0.2] * n,
        "rs_acceleration_zscore_nikkei": [0.3] * n,
        "rs31_topix": [1.1] * n,
        "rs31_nikkei": [1.2] * n,
        "rs63_topix": [1.1] * n,
        "rs63_nikkei": [1.2] * n,
        "rs126_topix": [1.1] * n,
        "rs126_nikkei": [1.2] * n,
        "rs252_topix": [1.1] * n,
        "rs252_nikkei": [1.2] * n,
        "rs_sma75_topix": [sma_topix] * n,
        "rs_sma75_nikkei": [sma_nikkei] * n,
    }
    row = {
        "code": "7203",
        "name": "Toyota",
        "date": as_of,
        "z_turnover_60": 0.1,
        "rs_acceleration_topix": 0.2,
        "rs_acceleration_nikkei": 0.3,
        "rs_acceleration_zscore_topix": 0.2,
        "rs_acceleration_zscore_nikkei": 0.3,
        "rs31_topix": 1.1,
        "rs31_nikkei": 1.2,
        "rs63_topix": 1.1,
        "rs63_nikkei": 1.2,
        "rs126_topix": 1.1,
        "rs126_nikkei": 1.2,
        "rs252_topix": 1.1,
        "rs252_nikkei": 1.2,
        "rs_sma75_topix": sma_topix,
        "rs_sma75_nikkei": sma_nikkei,
        "price_text": "text",
        "link_kabutan": "https://example.invalid/k",
        "turnover_ma_ratio_60": 1.5,
        "price_change_pct": 0.25,
        "perfect_order_days": 3,
        "beta_adjusted_rs_topix": 0.4,
        "beta_adjusted_rs_nikkei": 0.5,
        "information_ratio_topix": 0.6,
        "information_ratio_nikkei": 0.7,
    }
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE meta (
              as_of TEXT NOT NULL,
              source_csv_sha256 TEXT NOT NULL,
              freeze_utc TEXT NOT NULL,
              n_rows INTEGER NOT NULL,
              n_excluded INTEGER NOT NULL,
              axis_dates_json TEXT NOT NULL,
              note TEXT
            )
            """
        )
        conn.execute("CREATE TABLE rows (code TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE series (code TEXT PRIMARY KEY, metrics_json TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO meta VALUES (?,?,?,?,?,?,?)",
            (as_of, "a" * 64, "2026-10-03T00:00:00+00:00", 1, 0, json.dumps(axis), "test"),
        )
        conn.execute(
            "INSERT INTO rows VALUES (?,?)",
            ("7203", json.dumps(row, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO series VALUES (?,?)",
            (
                "7203",
                json.dumps({"dates_ref": "meta.axis_dates_json", "values": values}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_payloads_from_freeze_sqlite_projects_benches(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "freeze.sqlite"
    _write_sqlite(sqlite_path, sma_topix=0.91, sma_nikkei=0.82)
    projection = payloads_from_freeze_sqlite(
        sqlite_path,
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
    )
    payloads = projection.payloads
    assert projection.sma75_eligible["topix"] is None
    assert set(payloads) == {"topix", "nikkei"}
    for bench, payload in payloads.items():
        validate_web_asof_bundle(payload)
        assert payload["schema_id"] == SCHEMA_ID
        assert payload["benchmark"] == bench
        assert payload["rows"][0]["code"] == "7203"
        assert payload["rows"][0]["name"] == "Toyota"
        assert payload["series"]["7203"]["rs_sma75"][-1] == payload["rows"][0]["rs_sma75"]
        assert "sma75_lookback_eligible_topix" not in payload["rows"][0]
    assert payloads["topix"]["rows"][0]["rs_sma75"] == 0.91
    assert payloads["nikkei"]["rows"][0]["rs_sma75"] == 0.82
    assert payloads["topix"]["rows"][0]["rs31"] == 1.1
    assert payloads["nikkei"]["rows"][0]["rs31"] == 1.2
    assert payloads["topix"]["rows"][0]["turnover_ma_ratio_60"] == 1.5
    assert payloads["topix"]["rows"][0]["beta_adjusted_rs"] == 0.4
    assert payloads["nikkei"]["rows"][0]["beta_adjusted_rs"] == 0.5
    assert payloads["topix"]["rows"][0]["information_ratio"] == 0.6
    assert payloads["nikkei"]["rows"][0]["information_ratio"] == 0.7
    assert "turnover_yen" not in payloads["topix"]["rows"][0]
    paths = write_payload_files(payloads, tmp_path / "payloads")
    assert paths["topix"].is_file()
    assert paths["nikkei"].is_file()


def test_payloads_from_freeze_sqlite_rejects_low_sma75(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "freeze.sqlite"
    _write_sqlite(sqlite_path, sma_topix=None, sma_nikkei=0.82)
    with pytest.raises(AssembleWebAsofError, match="rs_sma75"):
        payloads_from_freeze_sqlite(
            sqlite_path,
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
        )


def test_universe_csv_from_ohlc_zip_lists_ticker_members(tmp_path: Path) -> None:
    import zipfile

    zip_path = tmp_path / "ohlc.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("7203.csv", "Date,Close\n")
        zf.writestr("135A.csv", "Date,Close\n")
        zf.writestr("readme.txt", "nope")
    dest = tmp_path / "universe.csv"
    n = write_universe_csv_from_ohlc_zip(zip_path, "2026-09-17", dest)
    assert n == 2
    text = dest.read_text(encoding="utf-8")
    assert "date,code,name" in text
    assert "2026-09-17,7203," in text
    assert "2026-09-17,135A," in text


def test_sma75_eligible_mask_excludes_short_history_nulls(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "freeze.sqlite"
    _write_sqlite(sqlite_path, sma_topix=0.91, sma_nikkei=0.82)
    conn = sqlite3.connect(str(sqlite_path))
    try:
        n = AXIS_LEN
        long_row = json.loads(
            conn.execute("SELECT payload_json FROM rows WHERE code='7203'").fetchone()[0]
        )
        long_row["sma75_lookback_eligible_topix"] = True
        long_row["sma75_lookback_eligible_nikkei"] = True
        short = dict(long_row)
        short["code"] = "9984"
        short["name"] = "Softbank"
        short["rs_sma75_topix"] = None
        short["rs_sma75_nikkei"] = None
        short["sma75_lookback_eligible_topix"] = False
        short["sma75_lookback_eligible_nikkei"] = False
        null_series = {
            "dates_ref": "meta.axis_dates_json",
            "values": {
                "z_turnover_60": [0.1] * n,
                "rs_acceleration_topix": [0.2] * n,
                "rs_acceleration_nikkei": [0.3] * n,
                "rs_acceleration_zscore_topix": [0.2] * n,
                "rs_acceleration_zscore_nikkei": [0.3] * n,
                "rs31_topix": [1.1] * n,
                "rs31_nikkei": [1.2] * n,
                "rs63_topix": [1.1] * n,
                "rs63_nikkei": [1.2] * n,
                "rs126_topix": [1.1] * n,
                "rs126_nikkei": [1.2] * n,
                "rs252_topix": [1.1] * n,
                "rs252_nikkei": [1.2] * n,
                "rs_sma75_topix": [None] * n,
                "rs_sma75_nikkei": [None] * n,
            },
        }
        conn.execute(
            "UPDATE rows SET payload_json=? WHERE code='7203'",
            (json.dumps(long_row, ensure_ascii=False),),
        )
        conn.execute(
            "INSERT INTO rows VALUES (?,?)",
            ("9984", json.dumps(short, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO series VALUES (?,?)",
            ("9984", json.dumps(null_series, ensure_ascii=False)),
        )
        conn.execute("UPDATE meta SET n_rows=2")
        conn.commit()
    finally:
        conn.close()
    projection = payloads_from_freeze_sqlite(
        sqlite_path,
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
    )
    assert projection.sma75_eligible["topix"] == [True, False]
    assert projection.sma75_eligible["nikkei"] == [True, False]
    assert projection.payloads["topix"]["rows"][0]["code"] == "7203"
    assert projection.payloads["topix"]["rows"][0]["rs_sma75"] == 0.91
    assert projection.payloads["topix"]["rows"][1]["code"] == "9984"
    assert projection.payloads["topix"]["rows"][1]["rs_sma75"] is None


def test_catalog_from_registry_row_binds_v11_yaml() -> None:
    from stockradar.metrics.registry_spec import load_metric_set_spec

    spec = load_metric_set_spec(
        Path(__file__).resolve().parents[1] / "config" / "metrics" / "metric_set_v1_1.yaml"
    )
    set_id, fingerprint, yaml_name = catalog_from_registry_row(
        {
            "id": _SET,
            "set_fingerprint": spec.set_fingerprint,
            "set_key": spec.set_key,
        }
    )
    assert set_id == _SET
    assert fingerprint == spec.set_fingerprint
    assert yaml_name == "metric_set_v1_1.yaml"


def test_catalog_from_registry_row_rejects_v1_free_fingerprint() -> None:
    from stockradar.metrics.registry_spec import load_metric_set_spec

    v11 = load_metric_set_spec(
        Path(__file__).resolve().parents[1] / "config" / "metrics" / "metric_set_v1_1.yaml"
    )
    free = load_metric_set_spec(
        Path(__file__).resolve().parents[1]
        / "config"
        / "metrics"
        / "metric_set_v1_free.yaml"
    )
    with pytest.raises(AssembleWebAsofError, match="mismatch"):
        catalog_from_registry_row(
            {
                "id": _SET,
                "set_fingerprint": free.set_fingerprint,
                "set_key": v11.set_key,
            }
        )


def test_payloads_include_csv_source_when_provided(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "freeze.sqlite"
    _write_sqlite(sqlite_path, sma_topix=0.91, sma_nikkei=0.82)
    projection = payloads_from_freeze_sqlite(
        sqlite_path,
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
        csv_source="ohlc_universe",
    )
    assert projection.payloads["topix"]["csv_source"] == "ohlc_universe"
    validate_web_asof_bundle(projection.payloads["topix"])
