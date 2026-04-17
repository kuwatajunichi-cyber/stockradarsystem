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