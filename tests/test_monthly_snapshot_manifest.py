"""Tests for monthly snapshot manifest pure helpers."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from stockradar.storage.monthly_snapshot_manifest import MONTHLY_SNAPSHOT_SCHEMA_VERSION, build_monthly_object_keys, build_monthly_snapshot_manifest
_SHA = "a" * 64
@pytest.mark.unit
def test_build_monthly_object_keys_shape() -> None:
    keys = build_monthly_object_keys(monthly_tag="monthly-20260701-123", ipo_sha256=_SHA, ipo_size=10, illiquid_sha256=_SHA, illiquid_size=20, core_sha256=_SHA, core_size=30, manifest_sha256=_SHA, manifest_size=40)
    assert keys["monthly_snapshots_schema_version"] == MONTHLY_SNAPSHOT_SCHEMA_VERSION
@pytest.mark.unit
def test_build_monthly_snapshot_manifest(tmp_path: Path) -> None:
    for name in ("equity_domestic_ipo_with_name.csv", "equity_domestic_illiquid_with_name.csv", "equity_domestic_core_with_name.csv"):
        (tmp_path / name).write_text("x", encoding="utf-8")
        (tmp_path / f"{name}.manifest.json").write_text(json.dumps({"output": {"sha256": _SHA, "size_bytes": 1}}), encoding="utf-8")
    manifest = build_monthly_snapshot_manifest(staging_dir=tmp_path, monthly_tag="monthly-20260701-1", github_run_id=1, snapshot_date="2026-07-01")
    assert manifest["manifest_kind"] == "monthly_snapshot"
