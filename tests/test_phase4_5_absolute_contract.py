"""Contract: Phase 4.5 absolute SSOT artifacts and gate schema v2 minimum."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stockradar.governance.phase4_5_absolute_contract import (
    validate_absolute_contract_artifacts,
    validate_forbidden_completion_without_evidence,
    validate_gate_schema_v2_minimum,
    validate_golden_vectors_fixture,
)

_REPO = Path(__file__).resolve().parents[1]
_GATE_STATUS = _REPO / "docs" / "operations" / "phase4_5_gate_status.yaml"

pytestmark = pytest.mark.unit


def _load_gate_status() -> dict:
    return yaml.safe_load(_GATE_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_absolute_contract_artifacts_present() -> None:
    violations = validate_absolute_contract_artifacts()
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_golden_vectors_fixture_valid() -> None:
    violations = validate_golden_vectors_fixture()
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_gate_schema_v2_minimum_on_real_yaml() -> None:
    data = _load_gate_status()
    assert data.get("schema_version") == 2
    violations = validate_gate_schema_v2_minimum(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_in_progress_gate_yaml_forbids_false_closed_claims() -> None:
    data = _load_gate_status()
    # Real SSOT may be closed with evidence; either way forbidden-completion must be empty.
    assert data.get("overall_status") in {"in_progress", "closed"}
    violations = validate_forbidden_completion_without_evidence(data)
    assert violations == [], "\n".join(violations)
    if data.get("overall_status") == "closed":
        live = data.get("live_gate_45c") or {}
        assert live.get("status") == "closed"
        soak = live.get("soak_run_urls") or []
        assert isinstance(soak, list) and len(soak) >= 3


@pytest.mark.unit
def test_pr45_1_artifacts_present() -> None:
    from stockradar.governance.phase4_5_absolute_contract import (
        validate_absolute_contract_artifacts_pr45_1,
    )

    violations = validate_absolute_contract_artifacts_pr45_1()
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_closed_overall_requires_live_and_capacity_evidence() -> None:
    data = _load_gate_status()
    closed = dict(data)
    closed["overall_status"] = "closed"
    live = dict(closed.get("live_gate_45c") or {})
    live["status"] = "open"
    closed["live_gate_45c"] = live
    violations = validate_forbidden_completion_without_evidence(closed)
    assert any("live_gate_45c closed" in v for v in violations)

    closed2 = dict(data)
    closed2["overall_status"] = "closed"
    capacity = dict(closed2.get("capacity_gate") or {})
    capacity["status"] = "open"
    closed2["capacity_gate"] = capacity
    violations2 = validate_forbidden_completion_without_evidence(closed2)
    assert any("capacity_gate closed" in v for v in violations2)


@pytest.mark.unit
def test_live_open_mutation_still_rejects_false_closed_overall() -> None:
    data = _load_gate_status()
    mutated = dict(data)
    mutated["overall_status"] = "closed"
    live = dict(mutated.get("live_gate_45c") or {})
    live["status"] = "open"
    mutated["live_gate_45c"] = live
    violations = validate_forbidden_completion_without_evidence(mutated)
    assert any("live_gate_45c closed" in v for v in violations)
