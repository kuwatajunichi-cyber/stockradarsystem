from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.job_integration


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workflow_text(name: str) -> str:
    return (_repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _load_workflow(name: str) -> dict[str, Any]:
    workflow = yaml.safe_load(_workflow_text(name))
    if not isinstance(workflow, dict):
        raise AssertionError(f"{name}: workflow must be a mapping")
    return workflow


def _workflow_on(workflow: Mapping[str, Any]) -> Mapping[str, Any]:
    on_block = workflow.get("on")
    if on_block is None:
        on_block = workflow.get(True)
    if not isinstance(on_block, Mapping):
        raise AssertionError("workflow 'on' block must be a mapping")
    return on_block


def _job(workflow: Mapping[str, Any], job_id: str) -> Mapping[str, Any]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, Mapping):
        raise AssertionError("workflow jobs must be a mapping")
    job = jobs.get(job_id)
    if not isinstance(job, Mapping):
        raise AssertionError(f"{job_id}: job must be a mapping")
    return job


def _step_named(job: Mapping[str, Any], step_name: str) -> Mapping[str, Any]:
    for step in job.get("steps", []) or []:
        if isinstance(step, Mapping) and step.get("name") == step_name:
            return step
    raise AssertionError(f"step not found: {step_name}")


def _step_with_id(job: Mapping[str, Any], step_id: str) -> Mapping[str, Any]:
    for step in job.get("steps", []) or []:
        if isinstance(step, Mapping) and step.get("id") == step_id:
            return step
    raise AssertionError(f"step id not found: {step_id}")


def _schedule_crons(workflow: Mapping[str, Any]) -> list[str]:
    on_block = _workflow_on(workflow)
    schedule = on_block.get("schedule", [])
    if not isinstance(schedule, list):
        raise AssertionError("workflow schedule must be a list")
    crons: list[str] = []
    for item in schedule:
        if not isinstance(item, Mapping):
            raise AssertionError("schedule entry must be a mapping")
        cron = item.get("cron")
        if not isinstance(cron, str):
            raise AssertionError("schedule cron must be a string")
        crons.append(cron)
    return crons


def test_test_yml_matches_reusable_quality_gate_marker_pipeline() -> None:
    workflow = _load_workflow("test.yml")
    gate = _load_workflow("reusable_quality_gate.yml")

    jobs = workflow["jobs"]
    assert list(jobs) == ["unit", "job_integration", "smoke", "worker"]
    assert jobs["job_integration"]["needs"] == "unit"
    assert jobs["smoke"]["needs"] == "job_integration"
    assert jobs["worker"]["needs"] == "smoke"

    unit = _job(workflow, "unit")
    assert _step_named(unit, "Set up Python")["with"]["python-version"] == "3.11"
    assert 'pip install -e ".[dev]"' in _step_named(unit, "Install dependencies")["run"]
    assert _step_named(unit, "Ruff")["run"].strip() == "ruff check src tests scripts"
    assert _step_named(unit, "Mypy")["run"].strip() == "mypy src/stockradar/jobs src/stockradar/indicators"

    preflight = _job(gate, "preflight")
    assert _step_named(preflight, "Set up Python")["with"]["python-version"] == "${{ inputs.python-version }}"
    assert _step_named(preflight, "Ruff")["run"].strip() == _step_named(unit, "Ruff")["run"].strip()
    assert _step_named(preflight, "Mypy")["run"].strip() == _step_named(unit, "Mypy")["run"].strip()
    assert _step_named(preflight, "Unit")["run"].strip() == _step_named(unit, "Unit tests")["run"].strip()
    assert _step_named(preflight, "Job integration")["run"].strip() == _step_named(
        _job(workflow, "job_integration"), "Job integration tests"
    )["run"].strip()
    assert _step_named(preflight, "Smoke")["run"].strip() == _step_named(
        _job(workflow, "smoke"), "Smoke tests"
    )["run"].strip()
    assert _step_named(_job(workflow, "worker"), "Worker unit tests")["run"].strip() == _step_named(
        preflight, "Worker cron dispatcher tests"
    )["run"].strip()
    actionlint_run = _step_named(preflight, "Actionlint")["run"]
    assert "rhysd/actionlint/v1.7.12/scripts/download-actionlint.bash" in actionlint_run
    assert 'bash -s -- "1.7.12"' in actionlint_run
    assert "./actionlint -color" in actionlint_run


def test_monthly_yml_uses_preflight_and_publishes_latest_three_csvs() -> None:
    workflow = _load_workflow("monthly.yml")
    build = _job(workflow, "build")

    assert _job(workflow, "preflight")["uses"] == "./.github/workflows/reusable_quality_gate.yml"
    assert build["needs"] == "preflight"
    assert build["permissions"]["contents"] == "write"

    release_step = _step_named(build, "Create Release")
    assert release_step["uses"] == "softprops/action-gh-release@v2"
    assert release_step["with"]["tag_name"] == "monthly-${{ steps.build_date.outputs.date }}-${{ github.run_id }}"
    assert release_step["with"]["fail_on_unmatched_files"] is True
    release_files = release_step["with"]["files"]
    assert "equity_domestic_ipo_with_name.csv" in release_files
    assert "equity_domestic_illiquid_with_name.csv" in release_files
    assert "equity_domestic_core_with_name.csv" in release_files

    upload_step = _step_named(build, "Upload latest 3 CSVs to all targets (work)")
    assert upload_step["env"]["PYTHONPATH"] == "."
    assert 'TARGETS="r2,dropbox,github"' in upload_step["run"]
    assert 'TARGETS="drive,r2,dropbox,github"' in upload_step["run"]
    assert 'python scripts/upload_to_all_targets.py --run-date "$RUN_DATE" --targets "$TARGETS" --files "$IPO" "$ILLIQ" "$CORE"' in upload_step["run"]


def test_monthly_yml_resolves_run_id_from_latest_and_staging() -> None:
    workflow = _load_workflow("monthly.yml")
    build = _job(workflow, "build")
    run_id_step = _step_named(build, "Get run ID from output")
    run_script = run_id_step["run"]
    assert 'cat data/output/latest/LATEST_RUN_ID.txt' in run_script
    assert "find data/output/staging -mindepth 1 -maxdepth 1 -type d" in run_script
    assert 'STAGING_DIR="data/output/staging/$RUN_ID"' in run_script

    release_step = _step_named(build, "Create Release")
    release_files = release_step["with"]["files"]
    assert "data/output/staging/${{ steps.get_run_id.outputs.run_id }}/equity_domestic_ipo_with_name.csv" in release_files
    assert "data/output/staging/${{ steps.get_run_id.outputs.run_id }}/equity_domestic_core_with_name.csv" in release_files


def test_daily_event_cause_enrichment_writes_enriched_csv_to_r2() -> None:
    workflow = _load_workflow("daily_event_cause_enrichment.yml")
    enrich = _job(workflow, "enrich")
    put_step = _step_named(enrich, "R2 shadow put enriched CSV staging")
    assert "artifact_bus_cli.py put" in put_step["run"]
    assert "--entry-id artifact-enriched-csv" in put_step["run"]
    get_step = _step_named(enrich, "R2 shadow validate indicators staging")
    assert "shadow-validate" in get_step["run"]
    assert "--entry-id artifact-daily-indicators" in get_step["run"]
    download_step = _step_named(enrich, "Download indicators artifact")
    assert download_step["uses"] == "actions/download-artifact@v4"
    upload_step = _step_named(enrich, "Upload enriched CSV artifact")
    assert upload_step["uses"] == "actions/upload-artifact@v4"


def test_daily_universe_patch_yml_resolves_monthly_tag_and_writes_single_patched_cache() -> None:
    text = _workflow_text("daily_universe_patch.yml")
    workflow = _load_workflow("daily_universe_patch.yml")

    assert text.count("actions/cache/save@v4") == 1
    assert "python -m stockradar.jobs.resolve_monthly_release_for_run_date" in text
    assert "python -m stockradar.jobs.patch_universe_daily" in text
    assert "python -m stockradar.jobs.cache_ops delete-key" in text
    assert "key: universe-patched-${{ steps.monthly.outputs.monthly_tag }}-${{ needs.resolve_trading_day.outputs.run_date }}" in text

    assert workflow["concurrency"]["group"] == "daily-universe-patch"
    assert workflow["concurrency"]["cancel-in-progress"] is False

    patch_job = _job(workflow, "patch_universe")
    assert patch_job["needs"] == "resolve_trading_day"
    assert patch_job["permissions"]["actions"] == "write"
    assert patch_job["permissions"]["contents"] == "read"


def test_render_sheet_workflow_supports_dispatch_and_call_contracts() -> None:
    workflow = _load_workflow("render_sheet.yml")
    on_block = _workflow_on(workflow)

    workflow_dispatch = on_block["workflow_dispatch"]
    workflow_call = on_block["workflow_call"]
    assert workflow_dispatch["inputs"]["csv_drive_file_id"]["required"] is True
    assert workflow_call["inputs"]["csv_drive_file_id"]["required"] is True
    assert workflow_call["outputs"]["spreadsheet_url"]["value"] == "${{ jobs.render.outputs.spreadsheet_url }}"

    render = _job(workflow, "render")
    assert render["outputs"]["spreadsheet_url"] == "${{ steps.run.outputs.spreadsheet_url }}"
    run_step = _step_with_id(render, "run")
    assert run_step["env"]["PYTHONPATH"] == "."
    assert "GDRIVE_OAUTH_CLIENT_ID" in run_step["env"]
    assert "python scripts/render_sheet/render_sheet.py" in run_step["run"]
    assert 'ARGS+=(--output-subfolder "${MONTH:0:7}")' in run_step["run"]


def test_gdrive_smoketest_a_calls_b_with_create_outputs() -> None:
    workflow = _load_workflow("gdrive_smoketest_A.yml")
    on_block = _workflow_on(workflow)

    assert "workflow_dispatch" in on_block

    create = _job(workflow, "create")
    create_step = _step_with_id(create, "create")
    assert "scripts/gdrive/smoketest/create_and_upload.py" in create_step["run"]

    call_b = _job(workflow, "call_b")
    assert call_b["needs"] == "create"
    assert call_b["uses"] == "./.github/workflows/gdrive_smoketest_B.yml"
    assert call_b["with"] == {
        "run_id": "${{ needs.create.outputs.run_id }}",
        "month_folder": "${{ needs.create.outputs.month_folder }}",
        "day_folder": "${{ needs.create.outputs.day_folder }}",
        "file_id": "${{ needs.create.outputs.file_id }}",
        "file_name": "${{ needs.create.outputs.file_name }}",
    }
    assert call_b["secrets"] == "inherit"


def test_gdrive_smoketest_b_requires_expected_inputs_and_process_script() -> None:
    workflow = _load_workflow("gdrive_smoketest_B.yml")
    on_block = _workflow_on(workflow)

    inputs = on_block["workflow_call"]["inputs"]
    assert inputs["run_id"]["required"] is True
    assert inputs["month_folder"]["required"] is True
    assert inputs["day_folder"]["required"] is True
    assert inputs["file_id"]["required"] is True
    assert inputs["file_name"]["default"] == ""

    job = _job(workflow, "fetch_process_upload")
    process_step = _step_with_id(job, "process")
    assert "scripts/gdrive/smoketest/fetch_process_upload.py" in process_step["run"]
    assert '--run-id "${{ inputs.run_id }}"' in process_step["run"]
    assert '--month-folder "${{ inputs.month_folder }}"' in process_step["run"]
    assert '--day-folder "${{ inputs.day_folder }}"' in process_step["run"]
    assert '--file-id "${{ inputs.file_id }}"' in process_step["run"]
    assert '--file-name "${{ inputs.file_name }}"' in process_step["run"]


def test_cleanup_artifacts_workflow_dispatch_defaults_and_dry_run_switch() -> None:
    workflow = _load_workflow("cleanup_artifacts.yml")
    on_block = _workflow_on(workflow)

    assert on_block["workflow_dispatch"]["inputs"]["dry_run"]["default"] == "true"
    assert on_block["workflow_dispatch"]["inputs"]["config_path"]["default"] == "config/cleanup_artifacts.yaml"
    assert _schedule_crons(workflow) == ["0 4 * * *"]
    assert workflow["concurrency"]["group"] == "cleanup-artifacts"
    assert workflow["concurrency"]["cancel-in-progress"] is False

    cleanup = _job(workflow, "cleanup")
    run_step = _step_named(cleanup, "Run artifact cleanup script")
    assert run_step["env"]["DRY_RUN"] == "${{ github.event_name == 'schedule' && 'false' || (github.event.inputs.dry_run || 'true') }}"
    assert run_step["env"]["CONFIG_PATH"] == "${{ github.event.inputs.config_path || 'config/cleanup_artifacts.yaml' }}"
    assert 'python scripts/cleanup_artifacts.py --repo "${{ github.repository }}" --config "$CONFIG_PATH"' in run_step["run"]
    assert 'ARGS+=(--dry-run)' in run_step["run"]
    assert "## cleanup_artifacts" in _step_named(cleanup, "Summary")["run"]


@pytest.mark.parametrize(
    ("workflow_name", "cron", "step_name", "script_path", "secret_keys"),
    [
        (
            "cleanup_drive_work.yml",
            "0 3 1 * *",
            "Run Drive cleanup",
            "python scripts/gdrive/cleanup_work.py --today \"$(date -u +%Y-%m-%d)\"",
            {"GDRIVE_OAUTH_CLIENT_ID", "GDRIVE_OAUTH_CLIENT_SECRET", "GDRIVE_OAUTH_REFRESH_TOKEN"},
        ),
        (
            "cleanup_drive_paid.yml",
            "5 3 1 * *",
            "Run Drive paid cleanup",
            "python scripts/gdrive/cleanup_paid.py --today \"$(date -u +%Y-%m-%d)\"",
            {"GDRIVE_OAUTH_CLIENT_ID", "GDRIVE_OAUTH_CLIENT_SECRET", "GDRIVE_OAUTH_REFRESH_TOKEN"},
        ),
        (
            "cleanup_dropbox.yml",
            "0 3 1 * *",
            "Run Dropbox cleanup",
            "python scripts/storage/dropbox_cleanup.py --today \"$(date -u +%Y-%m-%d)\"",
            {"DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN", "DROPBOX_BASE_FOLDER"},
        ),
        (
            "cleanup_r2.yml",
            "0 3 1 * *",
            "Run R2 cleanup",
            "python scripts/storage/r2_cleanup.py --today \"$(date -u +%Y-%m-%d)\"",
            {
                "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY",
                "R2_ACCOUNT_ID",
                "R2_BUCKET",
                "R2_BASE_PREFIX",
                "R2_ENDPOINT_URL",
            },
        ),
    ],
)
def test_storage_cleanup_workflows_call_expected_scripts(
    workflow_name: str, cron: str, step_name: str, script_path: str, secret_keys: set[str]
) -> None:
    workflow = _load_workflow(workflow_name)
    on_block = _workflow_on(workflow)

    assert "workflow_dispatch" in on_block
    assert _schedule_crons(workflow) == [cron]

    cleanup = _job(workflow, "cleanup")
    assert _step_named(cleanup, "Set up Python")["with"]["python-version"] == "3.11"
    assert "pip install -r requirements.txt" in _step_named(cleanup, "Install dependencies")["run"]

    run_step = _step_named(cleanup, step_name)
    assert secret_keys.issubset(set(run_step["env"]))
    run_body = run_step["run"].strip()
    assert run_body.startswith("set -euo pipefail")
    assert script_path in run_body
    if workflow_name == "cleanup_r2.yml":
        assert "python scripts/storage/runs_staging_cleanup.py --keep-days 14" in run_body
    else:
        assert run_body == f"set -euo pipefail\n{script_path}"


def test_cleanup_releases_workflow_deletes_daily_tags_older_than_three_months() -> None:
    workflow = _load_workflow("cleanup_releases.yml")
    on_block = _workflow_on(workflow)

    assert "workflow_dispatch" in on_block
    assert _schedule_crons(workflow) == ["0 3 1 * *"]

    cleanup = _job(workflow, "cleanup")
    run_step = _step_named(cleanup, "Compute cutoff and delete old daily releases")
    assert run_step["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert "gh release list --limit 500 --json tagName" in run_step["run"]
    assert "grep -E '^daily-[0-9]{6}$'" in run_step["run"]
    assert 'gh release delete "$tag" --yes --repo "${{ github.repository }}" || true' in run_step["run"]
