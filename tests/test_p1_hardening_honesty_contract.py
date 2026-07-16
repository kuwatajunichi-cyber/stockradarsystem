"""Contract: P1 hardening status SSOT must stay honest vs roadmap."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from stockradar.governance.p1_hardening_honesty import (
    validate_p1_roadmap_phrase,
    validate_p1_status_document,
)

_REPO = Path(__file__).resolve().parents[1]
_P1_STATUS = _REPO / "docs" / "operations" / "issue93_p1_hardening_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"


def _load_p1_status() -> dict:
    return yaml.safe_load(_P1_STATUS.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_p1_status_internal_consistency() -> None:
    data = _load_p1_status()
    violations = validate_p1_status_document(data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p1_roadmap_matches_status() -> None:
    data = _load_p1_status()
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    violations = validate_p1_roadmap_phrase(roadmap, data)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p1_closed_requires_all_evidence() -> None:
    good = {
        "overall_status": "closed",
        "p1_final_merge_commit": "abc1234567890abcd",
        "pr_p1_1_merge_commit": "abc1234567890abcd",
        "pr_p1_2_merge_commit": "abc1234567890abcd",
        "pr_p1_3_merge_commit": "abc1234567890abcd",
        "pr_p1_4_merge_commit": "abc1234567890abcd",
        "pr_p1_5_merge_commit": "abc1234567890abcd",
        "stale_running_before": 35,
        "stale_running_after": 0,
        "reconcile_applied_at_utc": "2026-07-16T14:30:00Z",
        "pytest_ci_run_url": "https://example.com/pytest",
        "daily_live_run_url": "https://example.com/daily",
        "stale_reconcile_run_url": "https://example.com/reconcile",
        "stale_before_snapshot_ref": "docs/operations/issue93_p1_baseline_snapshot.yaml",
        "stale_after_snapshot_ref": "docs/operations/issue93_p1_after_reconcile_snapshot.yaml",
        "observability_runbook_path": "docs/operations/issue93_p1_observability.md",
    }
    for n in range(1, 6):
        good[f"pr_p1_{n}_merge_ci_url"] = f"https://example.com/pr{n}"
    violations = validate_p1_status_document(good)
    assert violations == [], "\n".join(violations)


@pytest.mark.unit
def test_p1_closed_rejects_p0_migration_keys() -> None:
    bad = copy.deepcopy(_load_p1_status())
    bad["overall_status"] = "closed"
    bad["migration_merge_commit"] = "abc1234567890abcd"
    violations = validate_p1_status_document(bad)
    assert any("migration_merge_commit" in v for v in violations)


@pytest.mark.unit
def test_p1_closed_rejects_stale_after_not_less_than_before() -> None:
    bad = {
        "overall_status": "closed",
        "p1_final_merge_commit": "abc1234567890abcd",
        "pr_p1_1_merge_commit": "abc1234567890abcd",
        "pr_p1_2_merge_commit": "abc1234567890abcd",
        "pr_p1_3_merge_commit": "abc1234567890abcd",
        "pr_p1_4_merge_commit": "abc1234567890abcd",
        "pr_p1_5_merge_commit": "abc1234567890abcd",
        "stale_running_before": 10,
        "stale_running_after": 10,
        "reconcile_applied_at_utc": "2026-07-16T14:30:00Z",
        "pytest_ci_run_url": "https://example.com/pytest",
        "daily_live_run_url": "https://example.com/daily",
        "stale_reconcile_run_url": "https://example.com/reconcile",
        "stale_before_snapshot_ref": "docs/operations/issue93_p1_baseline_snapshot.yaml",
        "stale_after_snapshot_ref": "docs/operations/issue93_p1_after_reconcile_snapshot.yaml",
        "observability_runbook_path": "docs/operations/issue93_p1_observability.md",
    }
    for n in range(1, 6):
        bad[f"pr_p1_{n}_merge_ci_url"] = f"https://example.com/pr{n}"
    violations = validate_p1_status_document(bad)
    assert any("stale_running_after" in v for v in violations)


@pytest.mark.unit
def test_p1_roadmap_rejects_completion_while_local_only() -> None:
    data = _load_p1_status()
    bad = copy.deepcopy(data)
    bad["overall_status"] = "local_only"
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    import re

    bad_roadmap = re.sub(
        r"(^\|\s*\*\*P1\*\*\s*\|[^\n|]*\|)([^\n|]+)(\|\s*$)",
        lambda m: f"{m.group(1)}gate CLOSED (2026-07-16){m.group(3)}",
        roadmap,
        count=1,
        flags=re.MULTILINE,
    )
    violations = validate_p1_roadmap_phrase(bad_roadmap, bad)
    assert violations

@pytest.mark.unit
def test_merged_pending_live_requires_merge_and_ci_evidence() -> None:
    bad = {'overall_status': 'merged_pending_live'}
    violations = validate_p1_status_document(bad)
    assert any('merged_pending_live requires SHA-shaped pr_p1_1_merge_commit' in v for v in violations)
    assert any('merged_pending_live requires URL-shaped pr_p1_1_merge_ci_url' in v for v in violations)


@pytest.mark.unit
def test_merged_pending_live_accepts_full_merge_evidence() -> None:
    good = {'overall_status': 'merged_pending_live'}
    for n in range(1, 6):
        good[f'pr_p1_{n}_merge_commit'] = 'abc1234567890abcd'
        good[f'pr_p1_{n}_merge_ci_url'] = f'https://example.com/pr{n}'
    violations = validate_p1_status_document(good)
    assert violations == [], chr(10).join(violations)

@pytest.mark.unit
def test_local_only_rejects_p1_final_merge_commit() -> None:
    bad = {'overall_status': 'local_only', 'p1_final_merge_commit': 'abc1234567890abcd'}
    violations = validate_p1_status_document(bad)
    assert any('p1_final_merge_commit' in v for v in violations)


@pytest.mark.unit
def test_closed_requires_zero_stale_running_after() -> None:
    bad = {
        "overall_status": "closed",
        "p1_final_merge_commit": "abc1234567890abcd",
        "pr_p1_1_merge_commit": "abc1234567890abcd",
        "pr_p1_2_merge_commit": "abc1234567890abcd",
        "pr_p1_3_merge_commit": "abc1234567890abcd",
        "pr_p1_4_merge_commit": "abc1234567890abcd",
        "pr_p1_5_merge_commit": "abc1234567890abcd",
        "stale_running_before": 35,
        "stale_running_after": 34,
        "reconcile_applied_at_utc": "2026-07-16T14:30:00Z",
        "pytest_ci_run_url": "https://example.com/pytest",
        "daily_live_run_url": "https://example.com/daily",
        "stale_reconcile_run_url": "https://example.com/reconcile",
        "stale_before_snapshot_ref": "docs/operations/issue93_p1_baseline_snapshot.yaml",
        "stale_after_snapshot_ref": "docs/operations/issue93_p1_after_reconcile_snapshot.yaml",
        "observability_runbook_path": "docs/operations/issue93_p1_observability.md",
    }
    for n in range(1, 6):
        bad[f"pr_p1_{n}_merge_ci_url"] = f"https://example.com/pr{n}"
    violations = validate_p1_status_document(bad)
    assert any("stale_running_after: 0" in v for v in violations)


@pytest.mark.unit
def test_closed_rejects_non_string_p1_final_merge_commit() -> None:
    bad = {
        "overall_status": "closed",
        "p1_final_merge_commit": 123,
        "pr_p1_1_merge_commit": "abc1234567890abcd",
        "pr_p1_2_merge_commit": "abc1234567890abcd",
        "pr_p1_3_merge_commit": "abc1234567890abcd",
        "pr_p1_4_merge_commit": "abc1234567890abcd",
        "pr_p1_5_merge_commit": "abc1234567890abcd",
        "stale_running_before": 35,
        "stale_running_after": 0,
        "reconcile_applied_at_utc": "2026-07-16T14:30:00Z",
        "pytest_ci_run_url": "https://example.com/pytest",
        "daily_live_run_url": "https://example.com/daily",
        "stale_reconcile_run_url": "https://example.com/reconcile",
        "stale_before_snapshot_ref": "docs/operations/issue93_p1_baseline_snapshot.yaml",
        "stale_after_snapshot_ref": "docs/operations/issue93_p1_after_reconcile_snapshot.yaml",
        "observability_runbook_path": "docs/operations/issue93_p1_observability.md",
    }
    for n in range(1, 6):
        bad[f"pr_p1_{n}_merge_ci_url"] = f"https://example.com/pr{n}"
    violations = validate_p1_status_document(bad)
    assert any("p1_final_merge_commit" in v for v in violations)
