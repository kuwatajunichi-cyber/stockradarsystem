from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from stockradar.storage.mapping_catalog import phase2_daily_artifact_entry_ids, phase3_rollout_stage, phase4_rollout_stage

pytestmark = pytest.mark.job_integration

MAPPING_PATH = "config/github_state_to_r2_supabase_mapping.yaml"
PHASE2_DAILY_ENTRY_IDS = set(phase2_daily_artifact_entry_ids())
PHASE3_CACHE_ENTRY_IDS = frozenset(
    {
        "cache-index-store-zip-v1",
        "cache-ohlc-store-zip-v2",
        "cache-universe-patched",
        "cache-jpx-url",
    }
)
SCAN_WORKFLOWS = (
    "daily.yml",
    "daily_universe_patch.yml",
    "daily_event_cause_enrichment.yml",
    "monthly.yml",
    "monthly_new_core_backfill.yml",
    "monthly_new_core_backfill_dispatch.yml",
)
REQUIRED_FIELDS = (
    "source_kind",
    "source_name_pattern",
    "target_r2_key_pattern",
    "supabase_table",
    "retention_policy",
    "optional",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_mapping() -> dict[str, Any]:
    data = yaml.safe_load((_repo_root() / MAPPING_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("mapping YAML must be a mapping")
    return data


def _load_workflow(name: str) -> dict[str, Any]:
    data = yaml.safe_load((_repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{name}: workflow must be a mapping")
    return data


def _workflow_text(name: str) -> str:
    return (_repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _mapping_glob(pattern: str) -> str:
    return pattern.replace("YYYYMMDD", "*").replace("YYYYMM", "*")


def _normalize_name(raw: str) -> str:
    text = re.sub(r"\$\{\{\s*[^}]+\s*\}\}", "*", raw)
    return re.sub(r"\*+", "*", text)


def _iter_steps(workflow: Mapping[str, Any]):
    jobs = workflow.get("jobs")
    if not isinstance(jobs, Mapping):
        return
    for job in jobs.values():
        if not isinstance(job, Mapping):
            continue
        for step in job.get("steps", []) or []:
            if isinstance(step, Mapping):
                yield step


def _extract_upload_artifact_names(workflow: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for step in _iter_steps(workflow):
        if step.get("uses") != "actions/upload-artifact@v4":
            continue
        with_block = step.get("with") or {}
        name = with_block.get("name")
        if isinstance(name, str):
            names.add(_normalize_name(name))
    return names


def _extract_cache_keys(workflow: Mapping[str, Any], workflow_text: str) -> set[str]:
    keys: set[str] = set()
    for step in _iter_steps(workflow):
        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/cache"):
            with_block = step.get("with") or {}
            key = with_block.get("key")
            if isinstance(key, str) and "${{" not in key:
                keys.add(key)
            elif isinstance(key, str) and "patched_cache_key" in key:
                keys.add("universe-patched-*-*")
            elif isinstance(key, str) and "jpx-url" in key:
                keys.add("jpx-url-*")
    if "universe-patched-${" in workflow_text:
        keys.add("universe-patched-*-*")
    if "cache-index-store-zip-v1" in workflow_text:
        keys.add("index-store-zip-v1")
    if "cache-ohlc-store-zip-v2" in workflow_text:
        keys.add("ohlc-store-zip-v2")
    if "cache_bus_cli.py put-patched" in workflow_text:
        keys.add("universe-patched-*-*")
    return keys


def _extract_release_patterns(workflow: Mapping[str, Any], workflow_text: str) -> set[str]:
    patterns: set[str] = set()
    for step in _iter_steps(workflow):
        if step.get("uses") != "softprops/action-gh-release@v2":
            continue
        with_block = step.get("with") or {}
        tag = with_block.get("tag_name")
        if isinstance(tag, str):
            patterns.add(_normalize_name(tag))
    if "upload_to_all_targets.py" in workflow_text:
        patterns.add("daily-YYYYMM")
    return patterns


def _extract_artifact_bus_entry_ids(workflow_text: str) -> set[str]:
    return set(re.findall(r"--entry-id\s+(artifact-[a-z0-9-]+)", workflow_text))


def _entry_referenced_in_workflows(entry: dict[str, Any]) -> bool:
    entry_id = entry["id"]
    if entry_id in PHASE2_DAILY_ENTRY_IDS:
        for wf in (entry.get("writer_workflow"), entry.get("reader_workflow")):
            if not wf:
                continue
            text = _workflow_text(str(wf))
            if f"--entry-id {entry_id}" in text or f'--entry-id "{entry_id}"' in text:
                return True
        return False
    return False


def _matches_any_pattern(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(value, _mapping_glob(pattern)) for pattern in patterns)


def _collect_workflow_state() -> dict[str, dict[str, set[str]]]:
    state: dict[str, dict[str, set[str]]] = {}
    for wf in SCAN_WORKFLOWS:
        text = _workflow_text(wf)
        workflow = _load_workflow(wf)
        state[wf] = {
            "artifact": _extract_upload_artifact_names(workflow),
            "cache": _extract_cache_keys(workflow, text),
            "release": _extract_release_patterns(workflow, text),
        }
    return state


def test_mapping_yaml_required_fields_on_all_entries() -> None:
    mapping = _load_mapping()
    entries = mapping.get("entries")
    assert isinstance(entries, list) and entries
    for entry in entries:
        assert isinstance(entry, dict)
        for field in REQUIRED_FIELDS:
            assert field in entry, f"{entry.get('id', '?')}: missing {field}"
            if field == "optional":
                assert isinstance(entry[field], bool)
            else:
                assert entry[field], f"{entry.get('id', '?')}: empty {field}"


def test_mapping_scan_workflows_match_contract() -> None:
    mapping = _load_mapping()
    assert mapping.get("scan_workflows") == list(SCAN_WORKFLOWS)


def test_workflow_state_covered_by_mapping() -> None:
    mapping = _load_mapping()
    by_kind: dict[str, list[str]] = {"artifact": [], "cache": [], "release": []}
    for entry in mapping["entries"]:
        by_kind[entry["source_kind"]].append(entry["source_name_pattern"])

    workflow_state = _collect_workflow_state()
    for wf, kinds in workflow_state.items():
        for kind, names in kinds.items():
            for name in names:
                assert _matches_any_pattern(name, by_kind[kind]), (
                    f"{wf}: {kind} {name!r} not covered by mapping"
                )


def test_mapping_entries_exist_in_workflows() -> None:
    mapping = _load_mapping()
    workflow_state = _collect_workflow_state()
    all_artifacts: set[str] = set()
    all_caches: set[str] = set()
    all_releases: set[str] = set()
    for kinds in workflow_state.values():
        all_artifacts |= kinds["artifact"]
        all_caches |= kinds["cache"]
        all_releases |= kinds["release"]

    for entry in mapping["entries"]:
        kind = entry["source_kind"]
        pattern = entry["source_name_pattern"]
        writer = entry.get("writer_workflow")
        if writer and writer not in SCAN_WORKFLOWS:
            pytest.fail(f"{entry['id']}: unknown writer_workflow {writer!r}")

        if kind == "artifact":
            if entry["id"] in PHASE2_DAILY_ENTRY_IDS:
                if not _entry_referenced_in_workflows(entry):
                    pytest.fail(
                        f"{entry['id']}: Phase 2 R2 bus entry-id not found in writer/reader workflows"
                    )
                continue
            pool = all_artifacts
        elif kind == "cache":
            if entry["id"] in PHASE3_CACHE_ENTRY_IDS:
                wf_name = str(entry.get("writer_workflow") or "")
                wf_text = _workflow_text(wf_name) if wf_name in SCAN_WORKFLOWS else ""
                if entry["id"] in wf_text or "cache_bus_cli.py" in wf_text:
                    continue
            pool = all_caches
        elif kind == "release":
            if entry["id"] == "release-monthly-build":
                monthly_wf = _workflow_text("monthly.yml")
                if "monthly_bus_cli.py commit-snapshot" in monthly_wf:
                    continue
            pool = all_releases
        else:
            pytest.fail(f"unknown source_kind: {kind!r}")

        if not any(_matches_any_pattern(name, [pattern]) for name in pool):
            pytest.fail(f"{entry['id']}: pattern {pattern!r} not found in scanned workflows")


def test_enriched_csv_writer_is_enrichment_workflow_not_daily() -> None:
    mapping = _load_mapping()
    enriched = next(e for e in mapping["entries"] if e["id"] == "artifact-enriched-csv")
    assert enriched["writer_workflow"] == "daily_event_cause_enrichment.yml"
    assert enriched.get("reader_workflow") == "daily.yml"

    daily_uploads = _extract_upload_artifact_names(_load_workflow("daily.yml"))
    assert not any("enriched-csv" in name for name in daily_uploads)


def test_daily_release_entry_points_to_upload_cli() -> None:
    mapping = _load_mapping()
    release = next(e for e in mapping["entries"] if e["id"] == "release-daily-yyyymm")
    assert release["writer_impl"] == "scripts/upload_to_all_targets.py"
    assert "upload_to_all_targets.py" in _workflow_text("daily.yml")


def test_phase2_indicators_token_mix_documented_in_mapping() -> None:
    mapping = _load_mapping()
    indicators = next(e for e in mapping["entries"] if e["id"] == "artifact-daily-indicators")
    assert "{run_id}" in indicators["target_r2_key_pattern"]
    assert "{run_date_compact}" in indicators["target_r2_key_pattern"]
    assert "daily-indicators-*" in indicators["source_name_pattern"]


def test_enrichment_is_daily_indicators_consumer_via_r2() -> None:
    text = _workflow_text("daily_event_cause_enrichment.yml")
    assert "--entry-id artifact-daily-indicators" in text
    indicators = next(
        e for e in _load_mapping()["entries"] if e["id"] == "artifact-daily-indicators"
    )
    assert indicators.get("reader_workflow") == "daily_event_cause_enrichment.yml"
    assert indicators.get("reader_job") == "enrich"


def test_mapping_phase3_rollout_stage() -> None:
    mapping = _load_mapping()
    assert mapping.get("schema_version") == 6
    assert mapping.get("phase3_rollout_stage") == "3c"
    assert phase3_rollout_stage() == "3c"
    assert phase4_rollout_stage() == "4c"
    phase45_stage = mapping.get("phase4_5_rollout_stage")
    assert phase45_stage in {"off", "4.5a", "4.5b", "4.5c"}


def test_phase4_migration_sql_contains_tables_and_rpc() -> None:
    sql_path = _repo_root() / "supabase" / "migrations" / "002_phase4_control_plane.sql"
    assert sql_path.is_file()
    text = sql_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS monthly_snapshots" in text
    assert "CREATE TABLE IF NOT EXISTS publish_status" in text
    assert "CREATE OR REPLACE FUNCTION commit_jpx_url_cache" in text
    assert "monthly_snapshots_sha256_matches_core" in text


def test_phase3_cache_entries_have_supabase_tables() -> None:
    mapping = _load_mapping()
    for entry in mapping["entries"]:
        if entry["id"] not in PHASE3_CACHE_ENTRY_IDS:
            continue
        assert entry.get("supabase_tables"), f"{entry['id']}: missing supabase_tables"
        assert entry.get("supabase_active_table"), f"{entry['id']}: missing supabase_active_table"
    patched = next(e for e in mapping["entries"] if e["id"] == "cache-universe-patched")
    assert patched.get("target_r2_object_keys", {}).get("csv")
    assert patched.get("target_r2_object_keys", {}).get("manifest")


def test_mapping_adr005_planned_block_does_not_cut_over_live_cache() -> None:
    mapping = _load_mapping()
    adr005 = mapping.get("adr005")
    assert isinstance(adr005, dict)
    assert adr005.get("status") == "proposed"
    assert adr005.get("feature_start_release_month") is None
    assert adr005.get("live_cache_protocol") == "immutable_pointer_cas"
    assert adr005.get("planned_cache_protocol") == "immutable_pointer_cas"
    planned_objects = adr005.get("planned_objects")
    assert isinstance(planned_objects, dict)
    for key in (
        "cache_index_immutable",
        "cache_ohlc_immutable",
        "seed_delta",
        "request_manifest",
        "history_quality_artifact",
    ):
        assert planned_objects.get(key), f"adr005.planned_objects missing {key}"
    assert "derived-inputs/" in str(planned_objects["seed_delta"])

    scan = mapping.get("scan_workflows")
    assert isinstance(scan, list)
    assert "monthly_new_core_backfill.yml" in scan
    assert "monthly_new_core_backfill_dispatch.yml" in scan
    planned_scan = adr005.get("planned_scan_workflows")
    assert isinstance(planned_scan, list)
    overlap = set(planned_scan) & set(scan)
    assert not overlap, f"planned_scan_workflows must not overlap live scan_workflows: {overlap}"

    index_entry = next(e for e in mapping["entries"] if e["id"] == "cache-index-store-zip-v1")
    ohlc_entry = next(e for e in mapping["entries"] if e["id"] == "cache-ohlc-store-zip-v2")
    assert index_entry["writer_workflow"] == "daily.yml"
    assert ohlc_entry["writer_workflow"] == "daily.yml"
    assert index_entry["target_r2_key_pattern"] == "cache/index-store-zip-v1/objects/sha256={object_sha256}.zip"
    assert ohlc_entry["target_r2_key_pattern"] == "cache/ohlc-store-zip-v2/objects/sha256={object_sha256}.zip"
    assert index_entry["retention_policy"] == "warm_cache_immutable_pointer_cas"
    assert ohlc_entry["retention_policy"] == "warm_cache_immutable_pointer_cas"
    assert "monthly_new_core_backfill.yml" not in (index_entry.get("writer_workflows") or [])
    assert index_entry.get("writer_workflow") == "daily.yml"
    assert "objects/sha256=" in index_entry["planned_target_r2_key_pattern"]
    assert "objects/sha256=" in ohlc_entry["planned_target_r2_key_pattern"]
    assert index_entry["planned_retention_policy"] == "warm_cache_immutable_pointer_cas"
    assert "monthly_new_core_backfill.yml" in index_entry["planned_writer_workflows"]
    assert "monthly_new_core_backfill.yml" not in (index_entry.get("writer_workflows") or [])
