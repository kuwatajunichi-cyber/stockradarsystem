from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

pytestmark = pytest.mark.job_integration

MONTHLY_CRON = "0 2 1 * *"
DAILY_CRON = "45 6 * * *"
UNIVERSE_PATCH_CRON = "0 3 * * *"
WORKER_ROOT = Path(__file__).resolve().parents[1] / "workers" / "github-cron-dispatcher"


def test_worker_constants_include_monthly_cron() -> None:
    constants = (WORKER_ROOT / "src" / "constants.js").read_text(encoding="utf-8")
    assert f'export const MONTHLY_CRON = "{MONTHLY_CRON}";' in constants


def test_wrangler_still_has_two_crons_before_monthly_cutover() -> None:
    wrangler = tomllib.loads((WORKER_ROOT / "wrangler.toml").read_text(encoding="utf-8"))
    assert wrangler["triggers"]["crons"] == [DAILY_CRON, UNIVERSE_PATCH_CRON]
