from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.job_integration

MAPPING_PATH = "config/github_state_to_r2_supabase_mapping.yaml"
SCAN_WORKFLOWS = (
    "daily.yml",
    "daily_universe_patch.yml",
    "daily_event_cause_enrichment.yml",
    "monthly.yml",
)
REQUIRED_FIELDS = (
    "source_kind",
    "source_name_pattern",
    "target_r2_key_pattern",
    "supabase_table",
    "retention_policy",
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
            assert field in entry and entry[field], f"{entry.get('id', '?')}: missing {field}"


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
            pool = all_artifacts
        elif kind == "cache":
            pool = all_caches
        elif kind == "release":
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
