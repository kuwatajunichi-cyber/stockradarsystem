from __future__ import annotations
from pathlib import Path
import pytest
import yaml
pytestmark = pytest.mark.job_integration
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
def test_wrangler_has_three_crons_at_phase4c() -> None:
    text = (_repo_root() / "workers/github-cron-dispatcher/wrangler.toml").read_text(encoding="utf-8")
    assert "0 2 1 * *" in text
def test_monthly_yml_retains_github_schedule_until_worker_live() -> None:
    workflow = yaml.safe_load((_repo_root() / ".github/workflows/monthly.yml").read_text(encoding="utf-8"))
    on_block = workflow.get("on") or workflow.get(True) or {}
    schedule = on_block.get("schedule") or []
    crons = [entry.get("cron") for entry in schedule if isinstance(entry, dict)]
    assert "0 2 1 * *" in crons
