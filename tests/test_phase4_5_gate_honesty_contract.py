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


@pytest.mark.unit
def test_preflight_blocker_closed_requires_evidence() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    bad["preflight_blockers"]["put_fixed_defect"]["status"] = "closed"
    bad["preflight_blockers"]["put_fixed_defect"]["closed_at_utc"] = "2026-07-23T00:00:00Z"
    violations = validate_gate_status_document(bad)
    assert any("evidence_digest" in v for v in violations)


@pytest.mark.unit
def test_budget_blocker_closed_requires_postgres_evidence_url() -> None:
    data = _load_gate_status()
    bad = copy.deepcopy(data)
    blocker = bad["preflight_blockers"]["supabase_r2_budget_fixture"]
    blocker["status"] = "closed"
    blocker["closed_at_utc"] = "2026-07-23T00:00:00Z"
    blocker["evidence_digest"] = "abc123"
    blocker["postgres_measurement_evidence_url"] = None
    violations = validate_gate_status_document(bad)
    assert any("postgres_measurement_evidence_url" in v for v in violations)


@pytest.mark.unit
def test_roadmap_extracts_phase45_row() -> None:
    phrase = extract_phase45_roadmap_phrase(
        "| 4.5 | 派生指標時系列基盤 | **設計改訂済み・条件付き GO（実装未着手）** |"
    )
    assert phrase == "**設計改訂済み・条件付き GO（実装未着手）**"
