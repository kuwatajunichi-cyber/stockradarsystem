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


def test_within_free_tier_rejects_warning_exceed() -> None:
    ok, reasons = within_free_tier(
        supabase_projection_bytes=SUPABASE_WARN_BYTES,
        r2_total_bytes=0,
    )
    assert ok is False
    assert reasons
