"""Contract: Phase 4.5 cutover workflow wiring (secrets, Fake forbidden, no CI fixture)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.job_integration

_REPO = Path(__file__).resolve().parents[1]
_DAILY = _REPO / ".github" / "workflows" / "daily.yml"
_BACKFILL = _REPO / ".github" / "workflows" / "derived_backfill.yml"
_RECONCILE = _REPO / ".github" / "workflows" / "derived_reconcile.yml"


def _text(path: Path) -> str:
    raw = path.read_bytes()
    assert raw.count(b"\x00") == 0, path
    return raw.decode("utf-8")


def _write_derived_job() -> dict:
    workflow = yaml.safe_load(_text(_DAILY))
    job = workflow["jobs"]["write_derived_generation"]
    assert isinstance(job, dict)
    return job


def _step_named(job: dict, name: str) -> dict:
    for step in job.get("steps") or []:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"step not found: {name}")


def test_daily_write_derived_step_passes_prod_secrets() -> None:
    step = _step_named(_write_derived_job(), "Write derived generation (normal)")
    env = step.get("env") or {}
    assert env.get("SUPABASE_URL")
    assert env.get("SUPABASE_SECRET_KEY")
    assert env.get("R2_ACCESS_KEY_ID")
    assert env.get("R2_SECRET_ACCESS_KEY")
    assert env.get("R2_BUCKET")
    run = str(step.get("run") or "")
    assert "DERIVED_GENERATION_FAKE" not in run
    assert "11111111-2222-3333-4444-555555555555" not in run
    assert "phase4_5_shadow_metric_set_version_id" in run


def test_daily_finalize_includes_write_derived_generation() -> None:
    workflow = yaml.safe_load(_text(_DAILY))
    needs = workflow["jobs"]["finalize_run"]["needs"]
    assert "write_derived_generation" in needs
    text = _text(_DAILY)
    assert "--write-derived-result" in text
    assert "needs.write_derived_generation.result" in text


def test_backfill_prod_path_forbids_ci_fixture() -> None:
    text = _text(_BACKFILL)
    prod_start = text.find("Derived backfill put-generation (prod adapters)")
    assert prod_start > 0
    prod = text[prod_start:]
    assert "tests/fixtures/phase45_ci_snapshot.json" not in prod
    assert "snapshot_r2_key" in prod
    assert "CI fixture forbidden" in prod
    assert "derived_bus_cli.py get-object" in prod


def test_reconcile_prod_path_forbids_ci_fixture() -> None:
    text = _text(_RECONCILE)
    prod_start = text.find("Derived reconcile put-generation (prod adapters)")
    assert prod_start > 0
    prod = text[prod_start:]
    assert "tests/fixtures/phase45_ci_snapshot.json" not in prod
    assert "snapshot_r2_key" in prod
    assert "CI fixture forbidden" in prod
    assert "derived_bus_cli.py get-object" in prod


def test_mapping_shadow_metric_set_id_empty_while_off() -> None:
    mapping = yaml.safe_load(
        (_REPO / "config" / "github_state_to_r2_supabase_mapping.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert mapping.get("phase4_5_rollout_stage") == "off"
    assert mapping.get("phase4_5_shadow_metric_set_version_id") == ""
