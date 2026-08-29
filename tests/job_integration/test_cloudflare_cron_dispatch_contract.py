"""Cloudflare Cron dispatch contract (Phase 1 daily/patch + Phase 4 monthly)."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

from stockradar.jobs.validate_daily_dispatch_run_date import validate_input

pytestmark = pytest.mark.job_integration

DAILY_CRON = "45 6 * * *"
UNIVERSE_PATCH_CRON = "0 3 * * *"
MONTHLY_CRON = "0 2 1 * *"
MNC_DISPATCH_CRON = "*/15 * * * *"
WORKER_ROOT = Path(__file__).resolve().parents[2] / "workers" / "github-cron-dispatcher"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _daily_on_block() -> dict:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    return wf.get("on") or wf.get(True) or {}


def test_daily_cron_constant_in_worker_sources() -> None:
    constants = (WORKER_ROOT / "src" / "constants.js").read_text(encoding="utf-8")
    assert f'export const DAILY_CRON = "{DAILY_CRON}";' in constants
    assert f'export const UNIVERSE_PATCH_CRON = "{UNIVERSE_PATCH_CRON}";' in constants
    assert f'export const MONTHLY_CRON = "{MONTHLY_CRON}";' in constants
    assert f'export const MNC_DISPATCH_CRON = "{MNC_DISPATCH_CRON}";' in constants

    wrangler = tomllib.loads((WORKER_ROOT / "wrangler.toml").read_text(encoding="utf-8"))
    assert wrangler["triggers"]["crons"] == [
        DAILY_CRON,
        UNIVERSE_PATCH_CRON,
        MONTHLY_CRON,
        MNC_DISPATCH_CRON,
    ]
    assert wrangler["observability"]["enabled"] is True
    assert wrangler["observability"]["logs"]["invocation_logs"] is True
    assert wrangler["vars"].get("MNC_DISPATCH_ENABLED") == "false"


def test_worker_scheduled_handler_awaits_dispatch() -> None:
    source = (WORKER_ROOT / "src" / "index.js").read_text(encoding="utf-8")
    assert "await handleScheduledCron(controller, env)" in source
    assert "ctx.waitUntil" not in source


def test_cron_dispatch_watchdog_workflow_matches_python_table() -> None:
    from stockradar.jobs.cron_dispatch_watchdog import WATCHDOG_CRON_TO_TARGET

    text = (_repo_root() / ".github/workflows/cron_dispatch_watchdog.yml").read_text(encoding="utf-8")
    for cron in WATCHDOG_CRON_TO_TARGET:
        assert f'cron: "{cron}"' in text
    assert "daily.yml" in text
    assert "daily_universe_patch.yml" in text
    assert "monthly.yml" in text
    assert "monthly_new_core_backfill_dispatch.yml" in text
    assert "mnc_poller" in text
    on_block = yaml.safe_load(text).get("on") or yaml.safe_load(text).get(True) or {}
    schedule = on_block.get("schedule") or []
    assert len(schedule) == len(WATCHDOG_CRON_TO_TARGET)

    assert "--report-only" in text
    assert "steps.fetch.outputs.workflow_file" in text
    loaded = yaml.safe_load(text)
    steps = loaded["jobs"]["check"]["steps"]
    verdict = next(step for step in steps if step.get("id") == "verdict")
    assert verdict.get("continue-on-error") is not True


def test_worker_routes_daily_patch_and_monthly_workflows() -> None:
    constants = (WORKER_ROOT / "src" / "constants.js").read_text(encoding="utf-8")
    assert "daily.yml" in constants
    assert "daily_universe_patch.yml" in constants
    assert "monthly.yml" in constants
    assert "monthly_new_core_backfill_dispatch.yml" in constants
    assert "MONTHLY_DISPATCH_ENABLED" in (WORKER_ROOT / "wrangler.toml").read_text(encoding="utf-8")
    assert 'MONTHLY_DISPATCH_ENABLED = "true"' in (WORKER_ROOT / "wrangler.toml").read_text(encoding="utf-8")
    assert 'MNC_DISPATCH_ENABLED = "false"' in (WORKER_ROOT / "wrangler.toml").read_text(encoding="utf-8")


def test_worker_dispatch_module_uses_github_dispatch_endpoint() -> None:
    dispatch_js = (WORKER_ROOT / "src" / "dispatch.js").read_text(encoding="utf-8")
    assert "/actions/workflows/" in dispatch_js
    assert "dispatches" in dispatch_js
    assert "204" in dispatch_js


def test_worker_does_not_log_dispatch_token() -> None:
    for rel in ("src/dispatch.js", "src/index.js"):
        source = (WORKER_ROOT / rel).read_text(encoding="utf-8")
        assert "console.log" not in source or "GH_DISPATCH_TOKEN" not in source.split("console.log", 1)[-1]
        assert not re.search(r"console\.(log|error|warn)\([^)]*env\.GH_DISPATCH_TOKEN", source)


def test_daily_yml_has_no_github_schedule_after_cloudflare_cutover() -> None:
    on_block = _daily_on_block()
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []


def test_daily_yml_keeps_workflow_dispatch_and_concurrency() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    on_block = _daily_on_block()
    assert "workflow_dispatch" in on_block
    inputs = on_block["workflow_dispatch"].get("inputs") or {}
    assert set(inputs) >= {"run_date", "skip_publish", "force_index"}
    assert wf["concurrency"]["group"] == "daily-indicators"
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_empty_run_date_is_schedule_equivalent() -> None:
    is_replay, parsed = validate_input("")
    assert is_replay is False
    assert parsed is None


def test_daily_universe_patch_yml_has_no_github_schedule_after_cloudflare_cutover() -> None:
    wf = yaml.safe_load(
        (_repo_root() / ".github/workflows/daily_universe_patch.yml").read_text(encoding="utf-8")
    )
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []
    assert "workflow_dispatch" in on_block


def test_monthly_yml_has_no_github_schedule_after_cloudflare_cutover() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/monthly.yml").read_text(encoding="utf-8"))
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []
    assert "workflow_dispatch" in on_block


@pytest.mark.parametrize(
    "workflow_file",
    [
        "cleanup_artifacts.yml",
        "cleanup_drive_work.yml",
        "cleanup_drive_paid.yml",
        "cleanup_dropbox.yml",
        "cleanup_r2.yml",
        "cleanup_releases.yml",
    ],
)
def test_other_workflow_schedules_unchanged(workflow_file: str) -> None:
    path = _repo_root() / ".github/workflows" / workflow_file
    if not path.exists():
        pytest.skip(f"{workflow_file} not present")
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule") or []
    assert len(schedule) >= 1, f"{workflow_file} must retain schedule"
