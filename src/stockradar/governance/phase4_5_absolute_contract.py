"""Phase 4.5 section 0 absolute contract - plan SSOT machine checks."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[3]

_REQUIRED_PLAN_TODO_IDS = (
    "step0-merge-ssot",
    "pr-45-1-pure",
    "pr-45-2-control-plane",
    "pr-45-3-derived-generation",
    "capacity-gate",
    "pr-45-4-cutover-live",
    "honesty-contract",
)

_REQUIRED_PR_GATE_IDS_V2 = frozenset(
    {"pr-45-1", "pr-45-2", "pr-45-3", "pr-45-4"}
)

_REQUIRED_HISTORICAL_PR_GATE_IDS_V2 = frozenset(
    {
        "pr-45-0-gate-ssot",
        "pr-45-0b-put-fixed",
        "pr-45-0c-layer1-poc",
        "pr-45-0d-budget",
        "pr-45-0e-registry",
    }
)

_REQUIRED_DOCS_STEP0 = (
    _REPO / "docs" / "adr" / "phase45_canonical_digest.md",
    _REPO / "tests" / "fixtures" / "phase45_golden_vectors.json",
)

_REQUIRED_DOCS_PR45_1 = (
    _REPO / "config" / "metrics" / "metric_set_v1.yaml",
    _REPO / "config" / "metrics" / "metric_set_v1_free.yaml",
)

_REQUIRED_MODULES_PR45_1 = (
    _REPO / "src" / "stockradar" / "metrics" / "canonicalize.py",
)

_REQUIRED_MODULES_PR45_2 = (
    _REPO / "src" / "stockradar" / "storage" / "phase4_5_rollout.py",
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _load_gate_status() -> dict[str, Any]:
    path = _REPO / "docs" / "operations" / "phase4_5_gate_status.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_absolute_contract_artifacts() -> list[str]:
    """Step 0 minimum artifacts."""
    violations: list[str] = []
    for path in _REQUIRED_DOCS_STEP0:
        if not path.is_file():
            violations.append(f"missing required artifact: {path.relative_to(_REPO)}")
    return violations


def validate_absolute_contract_artifacts_pr45_1() -> list[str]:
    violations = validate_absolute_contract_artifacts()
    for path in _REQUIRED_DOCS_PR45_1 + _REQUIRED_MODULES_PR45_1:
        if not path.is_file():
            violations.append(f"missing required artifact: {path.relative_to(_REPO)}")
    return violations


def validate_absolute_contract_artifacts_pr45_2() -> list[str]:
    """PR-45-2 adds rollout + migration 006."""
    violations = validate_absolute_contract_artifacts_pr45_1()
    for path in _REQUIRED_MODULES_PR45_2:
        if not path.is_file():
            violations.append(f"missing required artifact: {path.relative_to(_REPO)}")
    migration = _REPO / "supabase" / "migrations" / "006_phase45_generation_commit.sql"
    if not migration.is_file():
        violations.append("missing migration 006_phase45_generation_commit.sql")
    return violations


def validate_golden_vectors_fixture() -> list[str]:
    violations: list[str] = []
    path = _REPO / "tests" / "fixtures" / "phase45_golden_vectors.json"
    if not path.is_file():
        return ["phase45_golden_vectors.json missing"]
    data = json.loads(path.read_text(encoding="utf-8"))
    vectors = data.get("logical_digest_vectors")
    if not isinstance(vectors, list) or len(vectors) < 3:
        violations.append("golden vectors require >= 3 logical_digest_vectors")
        return violations
    import hashlib

    for item in vectors:
        name = item.get("name")
        expected_digest = item.get("digest")
        utf8 = item.get("utf8")
        if not isinstance(expected_digest, str) or not _SHA256_RE.match(expected_digest):
            violations.append(f"vector {name}: invalid digest")
            continue
        if isinstance(utf8, str):
            actual = hashlib.sha256(utf8.encode("utf-8")).hexdigest()
            if actual != expected_digest:
                violations.append(f"vector {name}: digest mismatch")
    return violations


def validate_gate_schema_v2_minimum(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if data.get("schema_version") != 2:
        violations.append("phase4_5_gate_status.yaml must declare schema_version: 2")
    pr_gates = data.get("pr_gates")
    if not isinstance(pr_gates, dict):
        violations.append("pr_gates mapping required")
        return violations
    missing = _REQUIRED_PR_GATE_IDS_V2 - set(pr_gates)
    if missing:
        violations.append(f"pr_gates missing v2 ids: {sorted(missing)}")
    historical = data.get("historical_pr_gates")
    if not isinstance(historical, dict):
        violations.append("historical_pr_gates mapping required for schema v2")
    else:
        missing_hist = _REQUIRED_HISTORICAL_PR_GATE_IDS_V2 - set(historical)
        if missing_hist:
            violations.append(
                f"historical_pr_gates missing required gate ids: {sorted(missing_hist)}"
            )
    capacity = data.get("capacity_gate")
    if not isinstance(capacity, dict):
        violations.append("capacity_gate section required for schema v2")
    elif "path" not in capacity or "status" not in capacity:
        violations.append("capacity_gate requires path and status")
    live = data.get("live_gate_45c")
    if not isinstance(live, dict):
        violations.append("live_gate_45c section required for schema v2")
    elif "status" not in live:
        violations.append("live_gate_45c requires status")
    return violations


def validate_forbidden_completion_without_evidence(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    overall = str(data.get("overall_status") or "")
    if overall != "closed":
        return violations
    live = data.get("live_gate_45c")
    if not isinstance(live, dict) or live.get("status") != "closed":
        violations.append("overall_status closed requires live_gate_45c closed")
    capacity = data.get("capacity_gate")
    if not isinstance(capacity, dict) or capacity.get("status") != "closed":
        violations.append("overall_status closed requires capacity_gate closed")
    soak = live.get("soak_run_urls") if isinstance(live, dict) else None
    if not isinstance(soak, list) or len(soak) < 3:
        violations.append("overall_status closed requires soak_run_urls length >= 3")
    return violations