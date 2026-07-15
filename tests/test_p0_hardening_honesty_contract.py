"""Contract: P0 hardening status SSOT must stay honest vs roadmap."""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from stockradar.governance.p0_hardening_honesty import (
    validate_p0_status_document,
    validate_roadmap_p0_phrase,
)

_REPO = Path(__file__).resolve().parents[1]
_P0_STATUS = _REPO / "docs" / "operations" / "issue93_p0_hardening_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"


def _load_p0_status() -> dict:
    return yaml.safe_load(_P0_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_p0_status_internal_consistency() -> None:
    data = _load_p0_status()
    violations = validate_p0_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p0_roadmap_matches_status() -> None:
    data = _load_p0_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    violations = validate_roadmap_p0_phrase(roadmap, data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p0_closed_requires_all_evidence() -> None:
    data = _load_p0_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "closed"
    bad["migration_merge_commit"] = "abc1234567890abcd"
    bad["advisor_p0_findings_remaining"] = 0
    bad["migration_applied_at_utc"] = "2026-07-16T00:00:00Z"
    bad["live_verification_deadline_jpx_trading_days"] = 3
    for key in (
        "pytest_ci_run_url",
        "migration_applied_evidence_url",
        "service_role_smoke_run_url",
        "anon_security_smoke_run_url",
        "patch_jpx_run_url",
        "daily_live_run_url",
        "monthly_live_run_url",
    ):
        bad[key] = "https://example.com/evidence"
    violations = validate_p0_status_document(bad)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p0_closed_rejected_without_advisor_zero() -> None:
    data = _load_p0_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "closed"
    bad["migration_merge_commit"] = "abc1234567890abcd"
    bad["advisor_p0_findings_remaining"] = 2
    bad["migration_applied_at_utc"] = "2026-07-16T00:00:00Z"
    bad["live_verification_deadline_jpx_trading_days"] = 3
    for key in (
        "pytest_ci_run_url",
        "migration_applied_evidence_url",
        "service_role_smoke_run_url",
        "anon_security_smoke_run_url",
        "patch_jpx_run_url",
        "daily_live_run_url",
        "monthly_live_run_url",
    ):
        bad[key] = "https://example.com/evidence"
    violations = validate_p0_status_document(bad)
    assert any("advisor_p0_findings_remaining" in v for v in violations)


@pytest.mark.unit
def test_p0_roadmap_rejects_completion_while_local_only() -> None:
    data = _load_p0_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    bad_roadmap = re.sub(
        r"(^\|\s*\*\*P0\*\*\s*\|[^\n|]*\|)([^\n|]+)(\|\s*$)",
        lambda m: f"{m.group(1)}P0 gate CLOSED{m.group(3)}",
        roadmap,
        count=1,
        flags=re.MULTILINE,
    )
    violations = validate_roadmap_p0_phrase(bad_roadmap, data)
    assert violations