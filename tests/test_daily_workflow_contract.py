from __future__ import annotations

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


def test_daily_event_cause_enrichment_indicators_artifact_contract() -> None:
    text = (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(encoding="utf-8")
    assert "daily-indicators-${{ inputs.run_date }}" in text


def _job_upload_artifact_names(job: dict) -> list[tuple[str, int | None]]:
    uploads: list[tuple[str, int | None]] = []
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("uses") != "actions/upload-artifact@v4":
            continue
        with_block = step.get("with") or {}
        name = with_block.get("name")
        retention = with_block.get("retention-days")
        if isinstance(name, str):
            uploads.append((name, int(retention) if retention is not None else None))
    return uploads


def test_daily_yml_upload_artifact_contract_by_job() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]

    assert _job_upload_artifact_names(jobs["resolve_core_csv"]) == [
        ("daily-core-csv-${{ github.run_id }}", 3),
        ("daily-core-quality-${{ github.run_id }}", 3),
    ]
    assert _job_upload_artifact_names(jobs["ensure_index_cache"]) == [
        ("daily-index-store-${{ github.run_id }}", 3),
    ]
    assert _job_upload_artifact_names(jobs["ensure_core_cache"]) == [
        ("daily-ohlc-store-${{ github.run_id }}", 3),
        ("stale-exclusions-${{ github.run_id }}", 3),
    ]
    assert _job_upload_artifact_names(jobs["compute_indicators"]) == [
        ("daily-indicators-${{ needs.resolve_trading_day.outputs.run_date }}", 7),
    ]
    assert _job_upload_artifact_names(jobs["render_and_upload"]) == []


def test_daily_yml_does_not_upload_enriched_csv() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    for job_id, job in wf["jobs"].items():
        for name, _retention in _job_upload_artifact_names(job):
            assert "enriched-csv" not in name, f"{job_id} must not upload enriched-csv"


def test_daily_yml_render_and_upload_reads_indicators_and_enriched() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    render = wf["jobs"]["render_and_upload"]
    download_names: list[str] = []
    for step in render.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("uses") != "actions/download-artifact@v4":
            continue
        name = (step.get("with") or {}).get("name")
        if isinstance(name, str):
            download_names.append(name)
    assert "daily-indicators-${{ needs.resolve_trading_day.outputs.run_date }}" in download_names
    assert "enriched-csv-${{ needs.resolve_trading_day.outputs.run_date }}" in download_names


def test_daily_yml_no_github_schedule_after_cloudflare_cutover() -> None:
    """Phase 1: daily.yml schedule removed; Cloudflare Cron is canonical."""
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []
    assert "workflow_dispatch" in on_block
    assert wf["concurrency"]["group"] == "daily-indicators"
    assert wf["concurrency"]["cancel-in-progress"] is False