"""Contract: freeze sqlite projects to web_asof_bundle_v1 payloads."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from stockradar.jobs.assemble_web_asof import (
    AssembleWebAsofError,
    payloads_from_freeze_sqlite,
    write_payload_files,
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
    payloads = payloads_from_freeze_sqlite(
        sqlite_path,
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
    )
    assert set(payloads) == {"topix", "nikkei"}
    for bench, payload in payloads.items():
        validate_web_asof_bundle(payload)
        assert payload["schema_id"] == SCHEMA_ID
        assert payload["benchmark"] == bench
        assert payload["rows"][0]["code"] == "7203"
        assert payload["rows"][0]["name"] == "Toyota"
        assert payload["series"]["7203"]["rs_sma75"][-1] == payload["rows"][0]["rs_sma75"]
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
