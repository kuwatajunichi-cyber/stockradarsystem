"""Optional live smoke for Phase 1 dispatch (excluded from CI marker subset)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_dispatch

ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke" / "phase1_cloudflare_dispatch_smoke.py"


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_DISPATCH_SMOKE", "").lower() != "true",
    reason="Set RUN_LIVE_DISPATCH_SMOKE=true to run manual live smoke",
)
def test_phase1_dispatch_smoke_dry_run() -> None:
    """Runs smoke script without live dispatch; safe when gh auth or .env token exists."""
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 2), result.stdout + result.stderr
