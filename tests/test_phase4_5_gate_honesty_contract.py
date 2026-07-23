"""Contract: Phase 4.5 gate SSOT must stay honest vs roadmap."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from stockradar.governance.phase4_5_gate_honesty import (
    extract_phase45_roadmap_phrase,
    validate_gate_status_document,
    validate_roadmap_against_gate_status,
)

_REPO = Path(__file__).resolve().parents[1]
_GATE_STATUS = _REPO / "docs" / "operations" / "phase4_5_gate_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"


def _load_gate_status() -> dict:
    return yaml.safe_load(_GATE_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_phase4_5_gate_status_internal_consistency() -> None:
    data = _load_gate_status()
    violations = validate_gate_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase4_5_roadmap_matches_gate_status() -> None:
    data = _load_gate_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    violations = validate_roadmap_against_gate_status(roadmap, data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_phase4_gate_status_unchanged_still_closed() -> None:
    from stockradar.governance.phase_gate_honesty import validate_gate_status_document

    phase4_path = _REPO / "docs" / "operations" / "phase4_gate_status.yaml"
    data = yaml.safe_load(phase4_path.read_text(encoding="utf-8"))
    violations = validate_gate_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_in_progress_rejects_closed_roadmap_phrase() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["roadmap"]["phase45_status_phrase"] = "gate CLOSED"
    roadmap = "| 4.5 | Phase 4.5 | **gate CLOSED** |"
    violations = validate_roadmap_against_gate_status(roadmap, bad)
    assert any("must not claim completion" in v for v in violations)


_VALID_DIGEST = "a" * 64
_VALID_EVIDENCE_PATH = "docs/operations/evidence/phase45_fixture.json"


@pytest.mark.unit
def test_preflight_blocker_closed_requires_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["preflight_blockers"]["put_fixed_defect"]["status"] = "closed"
    bad["preflight_blockers"]["put_fixed_defect"]["closed_at_utc"] = "2026-07-23T00:00:00Z"
    violations = validate_gate_status_document(bad)
    assert any("evidence_digest" in v for v in violations)
    assert any("evidence_url" in v for v in violations)


@pytest.mark.unit
def test_preflight_blocker_closed_rejects_placeholder_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    blocker = bad["preflight_blockers"]["put_fixed_defect"]
    blocker["status"] = "closed"
    blocker["closed_at_utc"] = "2026-07-23T00:00:00Z"
    blocker["evidence_digest"] = "abc123"
    blocker["evidence_url"] = "TBD"
    violations = validate_gate_status_document(bad)
    assert any("SHA256-shaped evidence_digest" in v for v in violations)
    assert any("evidence_url" in v for v in violations)


@pytest.mark.unit
def test_budget_blocker_closed_requires_postgres_evidence_url() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    blocker = bad["preflight_blockers"]["supabase_r2_budget_fixture"]
    blocker["status"] = "closed"
    blocker["closed_at_utc"] = "2026-07-23T00:00:00Z"
    blocker["evidence_digest"] = _VALID_DIGEST
    blocker["evidence_url"] = _VALID_EVIDENCE_PATH
    blocker["postgres_measurement_evidence_url"] = None
    violations = validate_gate_status_document(bad)
    assert any("postgres_measurement_evidence_url" in v for v in violations)


@pytest.mark.unit
def test_roadmap_extracts_phase45_row() -> None:
    phrase = extract_phase45_roadmap_phrase(
        "| 4.5 | 派生指標時系列基盤 | **設計改訂済み・条件付き GO（実装未着手）** |"
    )
    assert phrase == "**設計改訂済み・条件付き GO（実装未着手）**"


@pytest.mark.unit
def test_preflight_closed_with_live_open_allows_in_progress() -> None:
    data = _load_gate_status()
    interim = copy.deepcopy(data)
    for blocker in interim["preflight_blockers"].values():
        blocker["status"] = "closed"
        blocker["closed_at_utc"] = "2026-07-23T00:00:00Z"
        blocker["evidence_digest"] = _VALID_DIGEST
        blocker["evidence_url"] = _VALID_EVIDENCE_PATH
    budget = interim["preflight_blockers"]["supabase_r2_budget_fixture"]
    budget["postgres_measurement_evidence_url"] = "https://example.com/pg"
    for gate in interim["pr_gates"].values():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "a" * 40
        gate["merge_ci_run_url"] = "https://github.com/org/repo/actions/runs/1"
        gate["pytest_ci_pass_on_merge"] = True
    interim["pr_gates"]["pr-45-0d-budget"]["postgres_measurement_evidence_url"] = (
        "https://example.com/pg"
    )
    interim["live_gate_45c"]["status"] = "open"
    interim["overall_status"] = "in_progress"
    violations = validate_gate_status_document(interim)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_live_gate_closed_requires_url_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["live_gate_45c"]["status"] = "closed"
    bad["live_gate_45c"]["closed_at_utc"] = "2026-07-23T00:00:00Z"
    bad["live_gate_45c"]["normal_daily_success_run_url"] = "TBD"
    violations = validate_gate_status_document(bad)
    assert any("live_gate_45c closed requires URL-shaped" in v for v in violations)


@pytest.mark.unit
def test_all_gates_closed_requires_overall_closed() -> None:
    data = _load_gate_status()
    good = copy.deepcopy(data)
    for blocker in good["preflight_blockers"].values():
        blocker["status"] = "closed"
        blocker["closed_at_utc"] = "2026-07-23T00:00:00Z"
        blocker["evidence_digest"] = _VALID_DIGEST
        blocker["evidence_url"] = _VALID_EVIDENCE_PATH
    good["preflight_blockers"]["supabase_r2_budget_fixture"]["postgres_measurement_evidence_url"] = (
        "https://example.com/pg"
    )
    for gate in good["pr_gates"].values():
        gate["status"] = "merged_and_verified"
        gate["merge_commit"] = "a" * 40
        gate["merge_ci_run_url"] = "https://github.com/org/repo/actions/runs/1"
        gate["pytest_ci_pass_on_merge"] = True
    good["pr_gates"]["pr-45-0d-budget"]["postgres_measurement_evidence_url"] = (
        "https://example.com/pg"
    )
    good["live_gate_45c"]["status"] = "closed"
    good["live_gate_45c"]["closed_at_utc"] = "2026-07-23T00:00:00Z"
    for key in (
        "normal_daily_success_run_url",
        "replay_no_shared_mutation_run_url",
        "backfill_shadow_only_run_url",
        "reconcile_isolated_run_url",
    ):
        good["live_gate_45c"][key] = "https://example.com/evidence"
    good["overall_status"] = "in_progress"
    good["roadmap"]["phase45_status_phrase"] = "gate CLOSED"
    violations = validate_gate_status_document(good)
    assert any("overall_status must be closed" in v for v in violations)
