"""Workflow contract: Healthchecks ping placement, if-guards, continue-on-error."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.job_integration

_REPO = Path(__file__).resolve().parents[2]
_DAILY = _REPO / ".github" / "workflows" / "daily.yml"
_PATCH = _REPO / ".github" / "workflows" / "daily_universe_patch.yml"
_MONTHLY = _REPO / ".github" / "workflows" / "monthly.yml"
_MNC = _REPO / ".github" / "workflows" / "monthly_new_core_backfill.yml"

CLOSED_PATCH = "Heartbeat (Healthchecks patch, closed day)"
OPEN_PATCH = "Heartbeat (Healthchecks patch)"
CLOSED_DAILY = "Heartbeat (Healthchecks daily, closed day)"
OPEN_DAILY = "Heartbeat (Healthchecks daily)"
MODULE = "python -m stockradar.observability.healthchecks_heartbeat"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step(job: dict, name: str) -> dict:
    for step in job.get("steps") or []:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def _step_index(job: dict, name: str) -> int:
    for i, step in enumerate(job.get("steps") or []):
        if isinstance(step, dict) and step.get("name") == name:
            return i
    raise AssertionError(f"missing step {name!r}")


def _heartbeat_steps(workflow: dict) -> list[dict]:
    found: list[dict] = []
    for job in (workflow.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and str(step.get("name") or "").startswith(
                "Heartbeat (Healthchecks"
            ):
                found.append(step)
    return found


def test_daily_closed_day_ping_in_resolve_job() -> None:
    wf = _load(_DAILY)
    job = wf["jobs"]["resolve_trading_day"]
    step = _step(job, CLOSED_DAILY)
    assert step.get("continue-on-error") is True
    assert "steps.resolve.outputs.is_open != 'True'" in str(step.get("if"))
    assert "success()" in str(step.get("if"))
    assert MODULE in step["run"]
    assert "|| true" not in step["run"]
    env = step["env"]
    assert env["HEALTHCHECKS_PING_URL"] == "${{ secrets.HEALTHCHECKS_DAILY_PING_URL }}"
    last = job["steps"][-1]
    assert last["name"] == CLOSED_DAILY
    cond = str(step.get("if"))
    assert "steps.validate_dispatch.outputs.is_replay != 'true'" in cond
    assert "is_replay != 'True'" not in cond
    assert "github.event.inputs.skip_publish != 'true'" in cond
    assert "outputs.skip_publish" not in cond
    names = [s.get("name") for s in job["steps"] if isinstance(s, dict)]
    assert OPEN_DAILY not in names


def test_daily_open_day_ping_after_upload_in_render_job() -> None:
    wf = _load(_DAILY)
    job = wf["jobs"]["render_and_upload"]
    step = _step(job, OPEN_DAILY)
    cond = str(step.get("if"))
    assert "needs.resolve_trading_day.outputs.is_open == 'True'" in cond
    assert "needs.resolve_trading_day.outputs.is_replay != 'true'" in cond
    assert "is_replay != 'True'" not in cond
    assert "github.event.inputs.skip_publish != 'true'" in cond
    assert "github.event.inputs.skip_publish" in cond
    assert "outputs.skip_publish" not in cond
    assert step.get("continue-on-error") is True
    assert MODULE in step["run"]
    assert "|| true" not in step["run"]
    upload_i = _step_index(job, "Upload to all targets (R2 / Dropbox; Drive optional)")
    ping_i = _step_index(job, OPEN_DAILY)
    assert ping_i > upload_i
    assert ping_i == len(job["steps"]) - 1


def test_patch_closed_and_open_ping_placement() -> None:
    wf = _load(_PATCH)
    resolve = wf["jobs"]["resolve_trading_day"]
    closed = _step(resolve, CLOSED_PATCH)
    assert closed.get("continue-on-error") is True
    assert "steps.resolve.outputs.is_open != 'True'" in str(closed.get("if"))
    assert MODULE in closed["run"]
    assert resolve["steps"][-1]["name"] == CLOSED_PATCH

    patch = wf["jobs"]["patch_universe"]
    opened = _step(patch, OPEN_PATCH)
    assert opened.get("continue-on-error") is True
    assert "needs.resolve_trading_day.outputs.is_open == 'True'" in str(
        opened.get("if")
    )
    assert "is_replay" not in str(opened.get("if"))
    assert "skip_publish" not in str(opened.get("if"))
    assert opened["env"]["HEALTHCHECKS_PING_URL"] == (
        "${{ secrets.HEALTHCHECKS_PATCH_PING_URL }}"
    )
    put_i = _step_index(patch, "Put patched universe cache (R2 + Supabase)")
    ping_i = _step_index(patch, OPEN_PATCH)
    assert ping_i == put_i + 1
    put = _step(patch, "Put patched universe cache (R2 + Supabase)")
    assert put.get("continue-on-error") is not True


def test_continue_on_error_only_on_heartbeat_steps() -> None:
    for path in (_DAILY, _PATCH):
        wf = _load(path)
        heartbeats = {id(s) for s in _heartbeat_steps(wf)}
        assert heartbeats, path.name
        for job in wf["jobs"].values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if step.get("continue-on-error") is True:
                    assert id(step) in heartbeats, step.get("name")


def test_heartbeat_step_count_and_job_split() -> None:
    daily = _load(_DAILY)
    patch = _load(_PATCH)
    assert len(_heartbeat_steps(daily)) == 2
    assert len(_heartbeat_steps(patch)) == 2
    render_names = [
        s.get("name")
        for s in daily["jobs"]["render_and_upload"]["steps"]
        if isinstance(s, dict)
    ]
    assert OPEN_DAILY in render_names
    assert CLOSED_DAILY not in render_names
    patch_resolve_names = [
        s.get("name")
        for s in patch["jobs"]["resolve_trading_day"]["steps"]
        if isinstance(s, dict)
    ]
    assert CLOSED_PATCH in patch_resolve_names
    assert OPEN_PATCH not in patch_resolve_names


def test_monthly_and_mnc_out_of_scope() -> None:
    for path in (_MONTHLY, _MNC):
        text = path.read_text(encoding="utf-8")
        assert "HEALTHCHECKS_" not in text
        assert "Heartbeat (Healthchecks" not in text
        assert "healthchecks_heartbeat" not in text
