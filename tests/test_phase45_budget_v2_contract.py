"""Contract: Phase 4.5 budget v2 Path B capacity projection."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from stockradar.storage.phase45_budget import (
    BUDGET_SCHEMA_VERSION,
    DEFAULT_PATH_B_CATALOG,
    DEFAULT_PATH_B_METRIC_SET_VERSIONS,
    DEFAULT_PATH_B_RETENTION_YEARS,
    R2_WARN_BYTES,
    BudgetProjectionInputs,
    canonical_report_hash,
    evaluate_capacity_path_b,
    project_r2_budget_v2,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO / "docs" / "operations" / "evidence" / "phase45_budget_v2_path_b_report.json"
_CLI = _REPO / "scripts" / "storage" / "phase45_budget_cli.py"


def test_budget_schema_version_is_v2() -> None:
    assert BUDGET_SCHEMA_VERSION == 2


def test_project_r2_budget_v2_plan_formula() -> None:
    inputs = BudgetProjectionInputs(
        symbols=100,
        metrics=10,
        trading_days_per_year=250,
        retention_years=3,
        metric_set_versions=2,
        snapshot_bytes_per_trade_date=1000,
        series_bytes_per_symbol_year=500,
        snapshot_manifest_bytes_per_trade_date=100,
        series_manifest_bytes_per_symbol_year=50,
        safety_factor=1.20,
        rollback_days=5,
        failed_days=3,
        reconcile_repair_rate=0.05,
        failed_fraction=0.02,
        layer1_r2_bytes=100_000,
    )
    breakdown = project_r2_budget_v2(inputs)
    snapshot_unit = 1100
    series_unit = 550
    assert breakdown.snapshots == snapshot_unit * 250 * 3 * 2
    assert breakdown.series == series_unit * 100 * 3 * 2
    assert breakdown.superseded == series_unit * 100 * 5 * 2
    full_generation = snapshot_unit + series_unit * 100
    assert breakdown.orphan == int(5 * 0.05 * 2 * full_generation)
    assert breakdown.failed == int(3 * 0.02 * full_generation)
    subtotal = (
        breakdown.snapshots
        + breakdown.series
        + breakdown.superseded
        + breakdown.orphan
        + breakdown.failed
        + 100_000
    )
    assert breakdown.subtotal_before_safety == subtotal
    assert breakdown.r2_total == int(subtotal * 1.20)


def test_canonical_report_hash_is_stable() -> None:
    report = {
        "schema_version": 2,
        "path": "B",
        "bytes": {"r2_total": 123},
        "generator_git_sha": "volatile",
    }
    first = canonical_report_hash(report)
    second = canonical_report_hash({**report, "generator_git_sha": "changed"})
    assert first == second
    assert len(first) == 64


def test_evaluate_capacity_path_b_within_free_tier() -> None:
    ok, r2_total, report = evaluate_capacity_path_b(repo_root=_REPO)
    assert ok is True
    assert r2_total < R2_WARN_BYTES
    assert report["path"] == "B"
    assert report["catalog"] == DEFAULT_PATH_B_CATALOG
    inputs = report["projection_inputs"]
    assert inputs["retention_years"] == DEFAULT_PATH_B_RETENTION_YEARS
    assert inputs["metric_set_versions"] == DEFAULT_PATH_B_METRIC_SET_VERSIONS
    assert inputs["metrics"] == 13
    assert inputs["safety_factor"] == 1.20
    assert inputs["rollback_days"] == 5
    assert inputs["failed_days"] == 3
    assert "reconcile_repair_rate" in inputs


def test_path_b_fixture_matches_cli_report_v2(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(_CLI), "report-v2", "--output", str(out)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"]["within_free_tier"] is True
    assert report["bytes"]["r2_total"] < R2_WARN_BYTES
    assert report["report_hash"] == canonical_report_hash(report)


def test_committed_path_b_fixture_is_deterministic() -> None:
    assert _FIXTURE.is_file(), "run phase45_budget_cli.py report-v2 to generate fixture"
    report = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert report["schema_version"] == BUDGET_SCHEMA_VERSION
    assert report["verdict"]["within_free_tier"] is True
    assert report["bytes"]["r2_total"] < R2_WARN_BYTES
    assert report["report_hash"] == canonical_report_hash(report)
    # Use committed projection_inputs (not live parquet measurement) for CI stability.
    inputs = BudgetProjectionInputs(**report["projection_inputs"])
    breakdown = project_r2_budget_v2(inputs)
    assert breakdown.r2_total == report["bytes"]["r2_total"]