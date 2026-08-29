from __future__ import annotations

import re
import subprocess
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


def test_daily_yml_no_actions_cache_phase3c() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert text.count("actions/cache/save@v4") == 0
    assert text.count("actions/cache/restore@v4") == 0
    assert "cache_ops rotate-delete" not in text
    assert "cache_bus_cli.py get-fixed" in text
    assert "cache_bus_cli.py put-immutable" in text
    assert "cache_bus_cli.py put-fixed" not in text
    assert "control_plane_cli.py upsert-run" in text
    assert 'PHASE3_ROLLOUT_STAGE: "3c"' in text


def _step_index(job: dict, step_name: str) -> int:
    for i, step in enumerate(job.get("steps", []) or []):
        if isinstance(step, dict) and step.get("name") == step_name:
            return i
    raise AssertionError(f"step not found: {step_name}")


def test_daily_yml_warm_cache_get_fixed_runs_after_install_dependencies() -> None:
    """Phase 3 warm cache restore requires runtime deps (httpx/boto3) before get-fixed."""
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    index_job = wf["jobs"]["ensure_index_cache"]
    ohlc_job = wf["jobs"]["ensure_core_cache"]
    assert _step_index(index_job, "Install dependencies") < _step_index(
        index_job, "Restore index store zip (R2 warm cache)"
    )
    assert _step_index(ohlc_job, "Install dependencies") < _step_index(
        ohlc_job, "Restore OHLC store zip (R2 warm cache)"
    )


def test_daily_yml_compute_and_resolve_no_cache_save() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "resolve_core_csv" in jobs
    assert "compute_indicators" in jobs
    _assert_job_has_no_cache_save(jobs["compute_indicators"], "compute_indicators")
    _assert_job_has_no_cache_save(jobs["resolve_core_csv"], "resolve_core_csv")


def test_daily_yml_resolve_core_csv_get_patched() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "cache_bus_cli.py get-patched" in text
    assert "--phase3-rollout-stage" in text
    materialize = text.split("Materialize core CSV + quality JSON", 1)[1].split("- name:", 1)[0]
    assert "R2_ACCESS_KEY_ID" in materialize
    assert "R2_BUCKET" in materialize


def test_daily_event_cause_enrichment_indicators_r2_contract() -> None:
    text = (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(
        encoding="utf-8"
    )
    assert "actions/download-artifact@v4" not in text
    assert "actions/upload-artifact@v4" not in text
    assert "artifact_bus_cli.py get" in text
    assert "record-fallback" not in text
    assert "shadow-validate" not in text
    assert "r2_fault_mode" not in text
    assert "--entry-id artifact-daily-indicators" in text
    assert "--entry-id artifact-enriched-csv" in text
    assert "github.run_id" in text


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


def test_daily_yml_phase2c_r2_only_handoff() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    daily_text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")

    assert "actions/upload-artifact@v4" not in daily_text
    assert "actions/download-artifact@v4" not in daily_text
    assert "record-fallback" not in daily_text
    assert "r2_fault_mode" not in daily_text
    assert "fallback_required" not in daily_text
    assert "validate_fault_injection" not in jobs

    resolve = jobs["resolve_core_csv"]
    assert not _job_has_upload_artifact(resolve, "daily-core-csv")
    assert "artifact_bus_cli.py put" in _job_steps_text(resolve)

    ensure_index = jobs["ensure_index_cache"]
    assert not _job_has_upload_artifact(ensure_index, "daily-index-store")
    assert "artifact_bus_cli.py put" in _job_steps_text(ensure_index)

    ensure_core = jobs["ensure_core_cache"]
    assert not _job_has_download_artifact(ensure_core, "daily-core-csv")
    assert not _job_has_upload_artifact(ensure_core, "daily-ohlc-store")
    assert "artifact_bus_cli.py get" in _job_steps_text(ensure_core)
    assert "record-fallback" not in _job_steps_text(ensure_core)

    compute = jobs["compute_indicators"]
    assert not _job_has_download_artifact(compute, "daily-ohlc-store")
    assert not _job_has_upload_artifact(compute, "daily-indicators")
    assert "artifact_bus_cli.py get" in _job_steps_text(compute)

    render = jobs["render_and_upload"]
    assert not _job_has_download_artifact(render, "daily-indicators")
    assert "artifact_bus_cli.py get" in _job_steps_text(render)

    assert "validated == 0" not in daily_text
    assert "stockradar.storage.handoff_summary" in daily_text
    assert "stockradar.storage.phase3_gate_summary" in daily_text
    assert "cache_source: ${{ steps.core_sel.outputs.cache_source }}" in daily_text


def _producer_put_steps(job: dict) -> list[dict]:
    steps: list[dict] = []
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if isinstance(run, str) and "artifact_bus_cli.py put" in run:
            steps.append(step)
    return steps


def _job_has_producer_handoff_summary(job: dict) -> bool:
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if isinstance(run, str) and "--mode producer" in run:
            return True
    return False


def test_daily_yml_producer_puts_have_supabase_secrets() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    for job_id in ("resolve_core_csv", "ensure_index_cache", "ensure_core_cache", "compute_indicators"):
        for step in _producer_put_steps(wf["jobs"][job_id]):
            env = step.get("env") or {}
            assert env.get("SUPABASE_URL") == "${{ secrets.SUPABASE_URL }}", job_id
            assert env.get("SUPABASE_SECRET_KEY") == "${{ secrets.SUPABASE_SECRET_KEY }}", job_id
            assert env.get("PHASE3_ROLLOUT_STAGE") == "${{ env.PHASE3_ROLLOUT_STAGE }}", job_id

    enrichment = yaml.safe_load(
        (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(encoding="utf-8")
    )
    for step in _producer_put_steps(enrichment["jobs"]["enrich"]):
        env = step.get("env") or {}
        assert env.get("SUPABASE_URL") == "${{ secrets.SUPABASE_URL }}"
        assert env.get("SUPABASE_SECRET_KEY") == "${{ secrets.SUPABASE_SECRET_KEY }}"
        assert env.get("PHASE3_ROLLOUT_STAGE") == "${{ env.PHASE3_ROLLOUT_STAGE }}"


def test_daily_yml_producer_puts_emit_json_fail_fast() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    producer_jobs = [
        "resolve_core_csv",
        "ensure_index_cache",
        "ensure_core_cache",
        "compute_indicators",
    ]
    for job_id in producer_jobs:
        puts = _producer_put_steps(wf["jobs"][job_id])
        assert puts, f"{job_id} must have producer put steps"
        for step in puts:
            run = step.get("run", "")
            assert "/tmp/r2_producer/" in run, job_id
            assert "--json-output" in run, job_id
            assert step.get("continue-on-error") is not True, job_id
            assert "set +e" not in run, job_id
        assert _job_has_producer_handoff_summary(wf["jobs"][job_id]), job_id


def test_daily_yml_producer_put_emits_manifest_key_on_success() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    for job_id in ("resolve_core_csv", "ensure_index_cache", "compute_indicators"):
        for step in _producer_put_steps(wf["jobs"][job_id]):
            run = step.get("run", "")
            assert 'if [ "$STATUS" = "ok" ]' not in run, job_id
            assert "manifest_logical_key" in run, job_id
            assert "GITHUB_OUTPUT" in run, job_id


def test_daily_yml_no_github_artifact_fallback_or_continue_on_error() -> None:
    text = (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    enrichment = (
        _repo_root() / ".github/workflows/daily_event_cause_enrichment.yml"
    ).read_text(encoding="utf-8")
    assert "shadow validation count is 0" not in text
    assert "shadow validation count is 0" not in enrichment
    assert "continue-on-error: true" not in text
    assert "continue-on-error: true" not in enrichment


def test_daily_yml_producer_manifest_outputs() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert jobs["resolve_core_csv"]["outputs"]["core_csv_manifest_key"]
    assert jobs["resolve_core_csv"]["outputs"]["core_quality_manifest_key"]
    assert jobs["ensure_index_cache"]["outputs"]["index_store_manifest_key"]
    assert jobs["ensure_core_cache"]["outputs"]["ohlc_store_manifest_key"]
    assert jobs["compute_indicators"]["outputs"]["daily_indicators_manifest_key"]


def test_daily_yml_render_and_upload_gets_indicators_and_enriched() -> None:
    render = yaml.safe_load(
        (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    )["jobs"]["render_and_upload"]
    text = _job_steps_text(render)
    step_names = [
        str(s.get("name"))
        for s in render.get("steps", [])
        if isinstance(s, dict) and s.get("name")
    ]
    assert "artifact_bus_cli.py get" in text
    assert "--entry-id artifact-daily-indicators" in text
    assert "--entry-id artifact-enriched-csv" in text
    assert "GitHub fallback indicators artifact" not in step_names


def test_no_tracked_files_under_data_indicators() -> None:
    root = _repo_root()
    tracked = subprocess.check_output(
        ["git", "ls-files", "data/indicators/"],
        cwd=root,
        text=True,
    ).strip()
    assert tracked == "", f"data/indicators/ must not be tracked: {tracked!r}"


def test_daily_yml_indicators_r2_put_uses_resolved_path_not_glob() -> None:
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    compute = wf["jobs"]["compute_indicators"]
    step_names = [
        str(s.get("name"))
        for s in compute.get("steps", [])
        if isinstance(s, dict) and s.get("name")
    ]
    assert "Resolve indicators csv path" in step_names
    assert "Upload indicators artifact" not in step_names
    r2_put = next(
        s
        for s in compute.get("steps", [])
        if isinstance(s, dict) and s.get("name") == "R2 put indicators staging"
    )
    assert "find data/indicators/daily" not in r2_put.get("run", "")
    put_env = r2_put.get("env") or {}
    assert put_env.get("INDICATORS_PATH") == "${{ steps.indicators_csv.outputs.path }}"


def test_daily_yml_no_github_schedule_after_cloudflare_cutover() -> None:
    """Phase 1: daily.yml schedule removed; Cloudflare Cron is canonical."""
    wf = yaml.safe_load((_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    on_block = wf.get("on") or wf.get(True) or {}
    schedule = on_block.get("schedule")
    assert schedule is None or schedule == []
    assert "workflow_dispatch" in on_block
    assert wf["concurrency"]["group"] == "daily-indicators"
    assert wf["concurrency"]["cancel-in-progress"] is False


def _daily_yml_text() -> str:
    return (_repo_root() / ".github/workflows/daily.yml").read_text(encoding="utf-8")


def _daily_yml() -> dict:
    return yaml.safe_load(_daily_yml_text())


def _step_blob(step: dict) -> str:
    parts: list[str] = []
    run = step.get("run")
    if isinstance(run, str):
        parts.append(run)
    env = step.get("env")
    if isinstance(env, dict):
        parts.append(yaml.dump(env))
    return "\n".join(parts)


def _steps_with_cli_command(job: dict, command: str) -> list[dict]:
    steps: list[dict] = []
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if command in _step_blob(step):
            steps.append(step)
    return steps


def test_daily_yml_no_r2_fault_mode_dispatch_input() -> None:
    wf = _daily_yml()
    on_block = wf.get("on") or wf.get(True) or {}
    inputs = on_block["workflow_dispatch"]["inputs"]
    assert "r2_fault_mode" not in inputs
    assert "Upload to all targets" in inputs["skip_publish"]["description"]
    assert "r2_fault_mode" not in inputs["run_date"]["description"]


def test_daily_yml_resolve_trading_day_needs_preflight_only() -> None:
    wf = _daily_yml()
    assert wf["jobs"]["resolve_trading_day"]["needs"] == "preflight"
    assert "validate_fault_injection" not in wf["jobs"]


def test_daily_yml_consumer_get_fail_fast() -> None:
    wf = _daily_yml()
    for job_id in ("ensure_core_cache", "compute_indicators", "render_and_upload"):
        job = wf["jobs"][job_id]
        for step in _steps_with_cli_command(job, "artifact_bus_cli.py get"):
            run = step.get("run", "")
            assert "set +e" not in run, job_id
            assert "fallback_required" not in run, job_id
            assert step.get("continue-on-error") is not True, job_id
            blob = _step_blob(step)
            assert "secrets.R2_BASE_PREFIX" in blob, job_id
            assert "fault-injection" not in blob, job_id


def test_daily_yml_render_and_upload_skip_publish_on_publish_step_only() -> None:
    wf = _daily_yml()
    render = wf["jobs"]["render_and_upload"]
    job_if = render["if"]
    assert "always()" in job_if
    assert "skip_publish" not in job_if
    text = _daily_yml_text()
    publish_idx = text.index("- name: Upload to all targets")
    publish_chunk = text[publish_idx : publish_idx + 1200]
    assert "if: github.event_name != 'workflow_dispatch' || github.event.inputs.skip_publish != 'true'" in publish_chunk
    assert "INVALID_FAULT_INJECTION" not in publish_chunk
    assert 'TARGETS="r2,dropbox"' in text
    upload_section = text.split("- name: Upload to all targets", 1)[1].split("- name: Publish to R2", 1)[0]
    assert "github" not in upload_section.split("TARGETS=", 1)[-1].split("\n", 3)[0]


def test_daily_yml_event_cause_enrichment_call_has_no_r2_fault_mode() -> None:
    text = _daily_yml_text()
    assert "r2_fault_mode" not in text


def test_daily_event_cause_enrichment_phase2c_r2_only() -> None:
    wf = yaml.safe_load(
        (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(
            encoding="utf-8"
        )
    )
    text = (_repo_root() / ".github/workflows/daily_event_cause_enrichment.yml").read_text(
        encoding="utf-8"
    )
    assert "control_plane_cli.py upsert-run" in text
    assert "--workflow daily_event_cause_enrichment.yml" in text
    on_block = wf.get("on") or wf.get(True) or {}
    inputs = on_block["workflow_call"]["inputs"]
    assert "r2_fault_mode" not in inputs
    enrich = wf["jobs"]["enrich"]
    get_step = next(
        s
        for s in enrich["steps"]
        if isinstance(s, dict) and s.get("name") == "R2 get indicators staging"
    )
    put_step = next(
        s
        for s in enrich["steps"]
        if isinstance(s, dict) and s.get("name") == "R2 put enriched CSV staging"
    )
    get_env = yaml.dump(get_step.get("env") or {})
    put_env = yaml.dump(put_step.get("env") or {})
    assert "fault-injection" not in get_env
    assert "fault-injection" not in put_env
    assert "secrets.R2_BASE_PREFIX" in get_env
    assert "secrets.R2_BASE_PREFIX" in put_env
    assert get_step.get("continue-on-error") is not True
    assert put_step.get("continue-on-error") is not True


def _step_by_name(job: dict, name: str) -> dict:
    for step in job.get("steps", []) or []:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"step not found: {name!r}")


def test_daily_yml_render_and_upload_r2_get_steps_define_run_date_compact() -> None:
    wf = _daily_yml()
    render = wf["jobs"]["render_and_upload"]
    get_steps = _steps_with_cli_command(render, "artifact_bus_cli.py get")
    assert len(get_steps) >= 2
    for step in get_steps:
        run = step.get("run", "")
        assert "RUN_DATE_COMPACT=" in run, step.get("name")
        compact_idx = run.index("RUN_DATE_COMPACT=")
        local_path_idx = run.index("${RUN_DATE_COMPACT}")
        assert compact_idx < local_path_idx, step.get("name")


def test_daily_yml_artifact_handoff_summary_steps_preserve_exit_code() -> None:
    wf = _daily_yml()
    for job_id, step_name in (
        ("compute_indicators", "Write compute_indicators artifact handoff summary"),
        ("render_and_upload", "Write render_and_upload artifact handoff summary"),
    ):
        step = _step_by_name(wf["jobs"][job_id], step_name)
        run = step.get("run", "")
        assert "RC=$?" in run, job_id
        assert 'exit "$RC"' in run, job_id
        assert "set +e" in run, job_id


def test_daily_yml_producer_summary_has_no_github_upload_ok_flag() -> None:
    text = _daily_yml_text()
    for step in re.findall(
        r"- name: Write .+ producer handoff summary\n(?:.*\n)*?        run: \|(?:.*\n)*?(?=\n      - name:|\n  [a-z_]+:)",
        text,
    ):
        assert "--github-upload-ok" not in step


def _handoff_summary_blocks(workflow_text: str) -> list[str]:
    return re.findall(
        r"python -m stockradar\.storage\.handoff_summary \\.*?(?=\n      - name:|\n  [a-z_]+:|\Z)",
        workflow_text,
        re.DOTALL,
    )


def _parse_handoff_summary_lists(block: str) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    for line in block.splitlines():
        stripped = line.strip().rstrip("\\").strip()
        if stripped.startswith("--required "):
            required.extend(stripped.removeprefix("--required ").split())
        elif stripped.startswith("--optional "):
            optional.extend(stripped.removeprefix("--optional ").split())
    return required, optional


def test_daily_workflows_handoff_summary_optional_matches_catalog() -> None:
    from stockradar.storage.mapping_catalog import get_entry, phase2_daily_artifact_entry_ids

    for workflow_name in ("daily.yml", "daily_event_cause_enrichment.yml"):
        text = (_repo_root() / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
        for block in _handoff_summary_blocks(text):
            required, optional = _parse_handoff_summary_lists(block)
            for entry_id in required + optional:
                if entry_id not in phase2_daily_artifact_entry_ids():
                    continue
                catalog_optional = bool(get_entry(entry_id).get("optional", False))
                if catalog_optional:
                    assert entry_id in optional, (workflow_name, entry_id, block)
                    assert entry_id not in required, (workflow_name, entry_id, block)
                else:
                    assert entry_id in required, (workflow_name, entry_id, block)
                    assert entry_id not in optional, (workflow_name, entry_id, block)


ENCODING_CONTRACT_FILES = (
    ".github/workflows/daily.yml",
    ".github/workflows/supabase_smoketest.yml",
    ".github/workflows/daily_event_cause_enrichment.yml",
    ".github/workflows/derived_backfill.yml",
    ".github/workflows/derived_reconcile.yml",
    "docs/contracts/github_state_to_r2_supabase_mapping.md",
    "docs/contracts/monthly_new_core_backfill_cloudflare_cron_dispatch.md",
    "docs/contracts/monthly_new_core_backfill.md",
    "docs/contracts/run_artifact_manifest_schema.md",
    "docs/operations/cloudflare_github_cron.md",
    "supabase/migrations/006_phase45_generation_commit.sql",
    "supabase/migrations/007_phase45_commit_expected_old_digest.sql",
)


@pytest.mark.parametrize("relative_path", ENCODING_CONTRACT_FILES)
def test_contract_files_are_utf8_without_bom(relative_path: str) -> None:
    raw = (_repo_root() / relative_path).read_bytes()
    assert raw.count(b"\x00") == 0, relative_path
    assert not raw.startswith(b"\xef\xbb\xbf"), relative_path
    raw.decode("utf-8")
