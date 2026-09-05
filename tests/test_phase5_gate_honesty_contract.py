"""Contract: Phase 5 gate SSOT must stay honest vs roadmap and cutover."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from stockradar.governance.phase5_gate_honesty import (
    REQUIRED_LIVE_GATE_IDS,
    REQUIRED_PR_GATE_IDS,
    extract_phase5_roadmap_phrase,
    validate_cutover_calendar_contract,
    validate_gate_status_document,
    validate_roadmap_against_gate_status,
)

_REPO = Path(__file__).resolve().parents[1]
_GATE_STATUS = _REPO / "docs" / "operations" / "phase5_gate_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"
_CUTOVER = _REPO / "docs" / "operations" / "phase5_observability_cutover.md"
_INDEX = _REPO / "docs" / "INDEX.md"


def _load_gate_status() -> dict:
    return yaml.safe_load(_GATE_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_phase5_gate_status_internal_consistency() -> None:
    data = _load_gate_status()
    violations = validate_gate_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase5_roadmap_matches_gate_status() -> None:
    data = _load_gate_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    violations = validate_roadmap_against_gate_status(roadmap, data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase5_cutover_calendar_contract() -> None:
    cutover = _CUTOVER.read_text(encoding="utf-8")
    violations = validate_cutover_calendar_contract(cutover)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase5_index_links_gate_ssot() -> None:
    index = _INDEX.read_text(encoding="utf-8")
    assert "phase5_gate_status.yaml" in index
    assert "phase5_observability_cutover.md" in index


@pytest.mark.unit
def test_phase5_required_gates_include_remaining_tracks() -> None:
    assert "pr-55a-healthchecks" in REQUIRED_PR_GATE_IDS
    remainder = REQUIRED_PR_GATE_IDS - {"pr-55a-healthchecks"}
    assert remainder, "pr_gates must not be 5.5a only"
    assert REQUIRED_LIVE_GATE_IDS - {"live_gate_55a"}


@pytest.mark.unit
def test_in_progress_rejects_closed_roadmap_phrase() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "in_progress"
    bad["roadmap"]["phase5_status_phrase"] = "gate CLOSED"
    roadmap = "| 5 | entitlements + observability | **gate CLOSED** |"
    violations = validate_roadmap_against_gate_status(roadmap, bad)
    assert any("must not claim completion" in v for v in violations)


@pytest.mark.unit
def test_extract_phase5_phrase_from_table() -> None:
    phrase = extract_phase5_roadmap_phrase(_ROADMAP.read_text(encoding="utf-8"))
    assert phrase is not None
    assert "in_progress" in phrase.lower()


def _mark_pr_merged(gate: dict) -> None:
    gate["status"] = "merged_and_verified"
    gate["merge_commit"] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    gate["merge_ci_run_url"] = "https://github.com/example/actions/runs/1"
    gate["pytest_ci_pass_on_merge"] = True
    for field in (
        "corrective_merge_commit",
        "corrective_ci_run_url",
        "merge_ci_failure_reason",
    ):
        gate.pop(field, None)


def _close_55a_only(data: dict) -> None:
    _mark_pr_merged(data["pr_gates"]["pr-55a-healthchecks"])
    for uid in ("u-55a-1", "u-55a-2"):
        data["user_gates"][uid]["status"] = "completed"
        data["user_gates"][uid]["evidence_url"] = "https://example.com/u-55a"
    live = data["live_gates"]["live_gate_55a"]
    live["status"] = "closed"
    live["closed_at_utc"] = "2026-09-10T00:00:00Z"
    for key in (
        "patch_success_ping_run_url",
        "daily_success_ping_run_url",
        "skip_publish_no_ping_run_url",
        "replay_no_ping_run_url",
        "closed_day_expected_ping_run_url",
    ):
        live[key] = "https://example.com/run"


@pytest.mark.unit
def test_55a_live_closed_keeps_overall_in_progress() -> None:
    data = _load_gate_status()
    good = copy.deepcopy(data)
    _close_55a_only(good)
    good["overall_status"] = "in_progress"
    violations = validate_gate_status_document(good)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_55a_live_closed_must_not_close_overall() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    _close_55a_only(bad)
    bad["overall_status"] = "closed"
    bad["roadmap"]["phase5_status_phrase"] = "gate CLOSED"
    violations = validate_gate_status_document(bad)
    assert any("all pr_gates merged_and_verified" in v for v in violations)
    assert any(
        "live_gate_55a alone is not enough" in v or "all live_gates closed" in v
        for v in violations
    )


@pytest.mark.unit
def test_55a_only_pr_gates_rejected() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["pr_gates"] = {
        "pr-55a-healthchecks": copy.deepcopy(data["pr_gates"]["pr-55a-healthchecks"])
    }
    violations = validate_gate_status_document(bad)
    assert any("missing required gate ids" in v for v in violations)


@pytest.mark.unit
def test_live_gate_55a_closed_requires_calendar_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    _close_55a_only(bad)
    bad["live_gates"]["live_gate_55a"]["closed_day_expected_ping_run_url"] = None
    violations = validate_gate_status_document(bad)
    assert any("closed_day_expected_ping_run_url" in v for v in violations)


@pytest.mark.unit
def test_cutover_rejects_closed_day_no_ping_policy() -> None:
    bad = (
        "# cutover\n"
        "closed_day_expected_ping\n"
        "is_replay\n"
        "skip_publish\n"
        "Watchdog\n"
        "continue-on-error\n"
        "**休場日:** パイプラインは is_open=False で skip → ping なし\n"
    )
    violations = validate_cutover_calendar_contract(bad)
    assert any("no-ping as the live calendar policy" in v for v in violations)
