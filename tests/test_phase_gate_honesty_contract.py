"""Contract: phase gate SSOT must stay honest vs roadmap (prevents false completion)."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from stockradar.governance.phase_gate_honesty import (
    validate_gate_status_document,
    validate_roadmap_against_gate_status,
)

_REPO = Path(__file__).resolve().parents[1]
_GATE_STATUS = _REPO / "docs" / "operations" / "phase4_gate_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"


def _load_gate_status() -> dict:
    return yaml.safe_load(_GATE_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_phase4_gate_status_internal_consistency() -> None:
    data = _load_gate_status()
    violations = validate_gate_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase4_roadmap_matches_gate_status() -> None:
    data = _load_gate_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    violations = validate_roadmap_against_gate_status(roadmap, data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase4_gate_status_allows_legitimate_closure_fixture() -> None:
    data = _load_gate_status()
    good = copy.deepcopy(data)
    good["overall_status"] = "closed"
    good["roadmap"]["phase4_status_phrase"] = "gate CLOSED"
    for gate_id, gate in good["pr_gates"].items():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "abc1234567890abcd"
        gate["pytest_ci_pass_on_merge"] = True
        if gate_id == "pr-4-1-ddl":
            gate["u1_ddl_applied"] = True
            gate["u1_evidence_url"] = "https://example.com/u1"
        if gate_id == "pr-4-3-resolve-4b":
            gate["live_gate_4b_evidence_url"] = "https://example.com/4b"
        if gate_id == "pr-4-6b-cutover":
            gate["u3_wrangler_deploy_evidence_url"] = "https://example.com/u3"
    good["live_gate_4c"]["status"] = "closed"
    good["live_gate_4c"]["closed_at_utc"] = "2026-07-10T00:00:00Z"
    for key in (
        "release_removed_daily_success_run_url",
        "publish_status_committed_run_url",
        "runs_status_run_url",
        "cron_dispatch_run_url",
    ):
        good["live_gate_4c"][key] = "https://example.com/evidence"
    violations = validate_gate_status_document(good)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_merged_and_verified_requires_user_gate_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    gate = bad["pr_gates"]["pr-4-1-ddl"]
    gate["status"] = "merged_and_verified"
    gate["merge_commit"] = "abc123"
    gate["pytest_ci_pass_on_merge"] = True
    violations = validate_gate_status_document(bad)
    assert any("u1_ddl_applied" in v or "u1_evidence_url" in v for v in violations)


@pytest.mark.unit
def test_missing_pr_gate_ids_rejected() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    del bad["pr_gates"]["pr-4-6b-cutover"]
    violations = validate_gate_status_document(bad)
    assert any("missing required gate ids" in v for v in violations)

@pytest.mark.unit
def test_merged_and_verified_pr_4_3_requires_4b_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    gate = bad["pr_gates"]["pr-4-3-resolve-4b"]
    gate["status"] = "merged_and_verified"
    gate["merge_commit"] = "abc123"
    gate["pytest_ci_pass_on_merge"] = True
    violations = validate_gate_status_document(bad)
    assert any("live_gate_4b_evidence_url" in v for v in violations)

@pytest.mark.unit
def test_merged_and_verified_rejects_non_url_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    gate = bad["pr_gates"]["pr-4-1-ddl"]
    gate["status"] = "merged_and_verified"
    gate["merge_commit"] = "abc123"
    gate["pytest_ci_pass_on_merge"] = True
    gate["u1_ddl_applied"] = True
    gate["u1_evidence_url"] = "TBD"
    violations = validate_gate_status_document(bad)
    assert any("URL-shaped u1_evidence_url" in v for v in violations)


@pytest.mark.unit
def test_closed_overall_status_rejects_in_progress_roadmap_phrase() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "closed"
    bad["roadmap"]["phase4_status_phrase"] = "実装済み（未マージ・live gate 未達）"
    for gate in bad["pr_gates"].values():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "abc123"
        gate["pytest_ci_pass_on_merge"] = True
    bad["live_gate_4c"]["status"] = "closed"
    bad["live_gate_4c"]["closed_at_utc"] = "2026-07-01T00:00:00Z"
    for key in (
        "release_removed_daily_success_run_url",
        "publish_status_committed_run_url",
        "runs_status_run_url",
        "cron_dispatch_run_url",
    ):
        bad["live_gate_4c"][key] = "https://example.com/evidence"
    violations = validate_gate_status_document(bad)
    assert any("overall_status closed but roadmap.phase4_status_phrase" in v for v in violations)

@pytest.mark.unit
def test_merged_and_verified_rejects_non_sha_merge_commit() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    gate = bad["pr_gates"]["pr-4-1-ddl"]
    gate["status"] = "merged_and_verified"
    gate["merge_commit"] = "TBD"
    gate["pytest_ci_pass_on_merge"] = True
    violations = validate_gate_status_document(bad)
    assert any("SHA-shaped merge_commit" in v for v in violations)


@pytest.mark.unit
def test_live_gate_closed_rejects_non_url_run_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "closed"
    bad["roadmap"]["phase4_status_phrase"] = "完了"
    for gate_id, gate in bad["pr_gates"].items():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "abc1234567890abcd"
        gate["pytest_ci_pass_on_merge"] = True
        if gate_id == "pr-4-1-ddl":
            gate["u1_ddl_applied"] = True
            gate["u1_evidence_url"] = "https://example.com/u1"
        if gate_id == "pr-4-3-resolve-4b":
            gate["live_gate_4b_evidence_url"] = "https://example.com/4b"
        if gate_id == "pr-4-6b-cutover":
            gate["u3_wrangler_deploy_evidence_url"] = "https://example.com/u3"
    bad["live_gate_4c"]["status"] = "closed"
    bad["live_gate_4c"]["closed_at_utc"] = "2026-07-10T00:00:00Z"
    for key in (
        "release_removed_daily_success_run_url",
        "publish_status_committed_run_url",
        "runs_status_run_url",
        "cron_dispatch_run_url",
    ):
        bad["live_gate_4c"][key] = "TBD"
    violations = validate_gate_status_document(bad)
    assert any("live_gate_4c closed requires URL-shaped" in v for v in violations)


@pytest.mark.unit
def test_roadmap_extracts_dated_closed_phrase() -> None:
    from stockradar.governance.phase_gate_honesty import extract_phase4_roadmap_phrase

    phrase = extract_phase4_roadmap_phrase("| 4 | Phase 4 | **gate CLOSED** (2026-07-10) |")
    assert phrase == "**gate CLOSED** (2026-07-10)"

@pytest.mark.unit
def test_roadmap_rejects_trailing_qualifiers_when_closed() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "closed"
    bad["roadmap"]["phase4_status_phrase"] = "gate CLOSED"
    for gate in bad["pr_gates"].values():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "abc1234567890abcd"
        gate["pytest_ci_pass_on_merge"] = True
    bad["live_gate_4c"]["status"] = "closed"
    bad["live_gate_4c"]["closed_at_utc"] = "2026-07-10T00:00:00Z"
    roadmap = "| 4 | Phase 4 | **gate CLOSED** (未マージヮlive gate 未達) |"
    violations = validate_roadmap_against_gate_status(roadmap, bad)
    assert any("must not claim in-progress when overall_status is closed" in v for v in violations)
