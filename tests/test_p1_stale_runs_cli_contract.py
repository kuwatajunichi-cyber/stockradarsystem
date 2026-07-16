from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_CLI = _REPO / "scripts" / "storage" / "control_plane_cli.py"


@pytest.mark.unit
def test_control_plane_cli_has_reconcile_stale_runs_subcommand() -> None:
    proc = subprocess.run(
        [sys.executable, str(_CLI), "reconcile-stale-runs", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--dry-run" in proc.stdout
    assert "--fail-if-any" in proc.stdout
    assert "--stale-after-hours" in proc.stdout
