from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.job_integration


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _assert_job_has_no_cache_save(job: object, job_id: str) -> None:
    if not isinstance(job, dict):
        raise AssertionError(f"{job_id}: job must be a mapping")
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/cache/save"):
            raise AssertionError(f"{job_id} must not use actions/cache/save, found {uses!r}")


def _job_steps_text(job: dict) -> str:
    parts: list[str] = []
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if isinstance(run, str):
            parts.append(run)
        uses = step.get("uses")
        if isinstance(uses, str):
            parts.append(uses)
        with_block = step.get("with") or {}
        name = with_block.get("name")
        if isinstance(name, str):
            parts.append(name)
    return "\n".join(parts)


def _job_artifact_bus_entry_ids(job: dict) -> list[str]:
    return re.findall(r"--entry-id\s+(artifact-[a-z0-9-]+)", _job_steps_text(job))


def _job_has_upload_artifact(job: dict, name_fragment: str) -> bool:
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("uses") != "actions/upload-artifact@v4":
            continue
        name = str((step.get("with") or {}).get("name", ""))
        if name_fragment in name:
            return True
    return False


def _job_has_download_artifact(job: dict, name_fragment: str) -> bool:
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("uses") != "actions/download-artifact@v4":
            continue
        name = str((step.get("with") or {}).get("name", ""))
        if name_fragment in name:
            return True
    return False


def test_daily_yml_no_patch_universe_job_in_daily() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "stockradar.jobs.patch_universe_daily" not in text


def test_daily_yml_exactly_two_cache_saves() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert text.count("actions/cache/save@v4") == 2


def test_daily_yml_compute_and_resolve_no_cache_save() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "resolve_core_csv" in jobs
    assert "compute_indicators" in jobs
    _assert_job_has_no_cache_save(jobs["compute_indicators"], "compute_indicators")
    _assert_job_has_no_cache_save(jobs["resolve_core_csv"], "resolve_core_csv")


def test_daily_yml_uses_rotate_delete_for_warm_cache() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "cache_ops rotate-delete" in text


def test_daily_event_cause_enrichment_indicators_r2_contract() -> None:
    text = (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(
        encoding="utf-8"
    )
    assert "actions/download-artifact@v4" in text
    assert "actions/upload-artifact@v4" in text
    assert "shadow-validate" in text
    assert "--entry-id artifact-daily-indicators" in text
    assert "--entry-id artifact-enriched-csv" in text


def test_daily_yml_r2_bus_contract_by_job() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]

    assert "artifact-daily-core-csv" in _job_artifact_bus_entry_ids(jobs["resolve_core_csv"])
    assert "artifact-daily-core-quality" in _job_artifact_bus_entry_ids(jobs["resolve_core_csv"])
    assert "artifact-daily-index-store" in _job_artifact_bus_entry_ids(jobs["ensure_index_cache"])
    ensure_core = _job_artifact_bus_entry_ids(jobs["ensure_core_cache"])
    assert "artifact-daily-ohlc-store" in ensure_core
    assert "artifact-stale-exclusions" in ensure_core
    compute = _job_artifact_bus_entry_ids(jobs["compute_indicators"])
    assert "artifact-daily-indicators" in compute
    assert "artifact-daily-ohlc-store" in compute
    render = _job_artifact_bus_entry_ids(jobs["render_and_upload"])
    assert "artifact-daily-indicators" in render
    assert "artifact-enriched-csv" in render


def test_daily_yml_phase2a_github_artifact_primary_with_r2_shadow() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]

    resolve = jobs["resolve_core_csv"]
    assert _job_has_upload_artifact(resolve, "daily-core-csv")
    assert _job_has_upload_artifact(resolve, "daily-core-quality")
    assert "artifact_bus_cli.py put" in _job_steps_text(resolve)

    ensure_index = jobs["ensure_index_cache"]
    assert _job_has_upload_artifact(ensure_index, "daily-index-store")
    assert "artifact_bus_cli.py put" in _job_steps_text(ensure_index)

    ensure_core = jobs["ensure_core_cache"]
    assert _job_has_download_artifact(ensure_core, "daily-core-csv")
    assert _job_has_upload_artifact(ensure_core, "daily-ohlc-store")
    assert "shadow-validate" in _job_steps_text(ensure_core)
    assert "artifact_bus_cli.py get" not in _job_steps_text(ensure_core)

    compute = jobs["compute_indicators"]
    assert _job_has_download_artifact(compute, "daily-ohlc-store")
    assert _job_has_upload_artifact(compute, "daily-indicators")
    assert "shadow-validate" in _job_steps_text(compute)
    assert "artifact_bus_cli.py get" not in _job_steps_text(compute)

    render = jobs["render_and_upload"]
    assert _job_has_download_artifact(render, "daily-indicators")
    assert _job_has_download_artifact(render, "enriched-csv")
    assert "shadow-validate" in _job_steps_text(render)
    assert "artifact_bus_cli.py get" not in _job_steps_text(render)


def test_daily_yml_producer_manifest_outputs() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert jobs["resolve_core_csv"]["outputs"]["core_csv_manifest_key"]
    assert jobs["resolve_core_csv"]["outputs"]["core_quality_manifest_key"]
    assert jobs["ensure_index_cache"]["outputs"]["index_store_manifest_key"]
    assert jobs["ensure_core_cache"]["outputs"]["ohlc_store_manifest_key"]
    assert jobs["compute_indicators"]["outputs"]["daily_indicators_manifest_key"]


def test_daily_yml_render_and_upload_shadow_validates_indicators_and_enriched() -> None:
    render = yaml.safe_load(
        (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    )["jobs"]["render_and_upload"]
    text = _job_steps_text(render)
    assert "shadow-validate" in text
    assert "--entry-id artifact-daily-indicators" in text
    assert "--entry-id artifact-enriched-csv" in text


def test_daily_yml_no_github_schedule_after_cloudflare_cutover() -> None:
    """Phase 1: daily.yml schedule removed; Cloudflare Cron is canonical."""
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []
    assert "workflow_dispatch" in on_block
    assert wf["concurrency"]["group"] == "daily-indicators"
    assert wf["concurrency"]["cancel-in-progress"] is False
