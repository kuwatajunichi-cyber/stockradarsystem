"""Pure validation for Issue #93 P0 hardening status SSOT."""
from __future__ import annotations

import re
from typing import Any

P0_STATUS_PLANNED = "planned"
P0_STATUS_LOCAL_ONLY = "local_only"
P0_STATUS_MERGED_PENDING_LIVE = "merged_pending_live"
P0_STATUS_CLOSED = "closed"

_TERMINAL = frozenset({P0_STATUS_CLOSED})
_NON_TERMINAL = frozenset({P0_STATUS_PLANNED, P0_STATUS_LOCAL_ONLY, P0_STATUS_MERGED_PENDING_LIVE})

_EVIDENCE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_MERGE_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)

_P0_ROADMAP_IN_PROGRESS_MARKERS = ("未完了", "着手前", "未実施", "in_progress", "pending")

_REQUIRED_CLOSED_URL_FIELDS = (
    "pytest_ci_run_url",
    "migration_applied_evidence_url",
    "service_role_smoke_run_url",
    "anon_security_smoke_run_url",
    "patch_jpx_run_url",
    "daily_live_run_url",
    "monthly_live_run_url",
)

_REQUIRED_CLOSED_SCALAR_FIELDS = (
    "migration_merge_commit",
    "advisor_p0_findings_remaining",
    "migration_applied_at_utc",
    "live_verification_deadline_jpx_trading_days",
)


def validate_p0_status_document(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    status = str(data.get("overall_status") or "")
    if status not in _TERMINAL | _NON_TERMINAL:
        violations.append(
            f"overall_status must be one of {sorted(_TERMINAL | _NON_TERMINAL)!r}, got {status!r}"
        )
        return violations

    if status == P0_STATUS_CLOSED:
        for field in _REQUIRED_CLOSED_SCALAR_FIELDS:
            if data.get(field) in (None, ""):
                violations.append(f"overall_status closed requires {field}")
        remaining = data.get("advisor_p0_findings_remaining")
        if remaining != 0:
            violations.append("overall_status closed requires advisor_p0_findings_remaining: 0")
        merge_commit = data.get("migration_merge_commit")
        if not isinstance(merge_commit, str) or not _MERGE_COMMIT_SHA_RE.match(merge_commit.strip()):
            violations.append("overall_status closed requires SHA-shaped migration_merge_commit")
        for field in _REQUIRED_CLOSED_URL_FIELDS:
            value = data.get(field)
            if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                violations.append(f"overall_status closed requires URL-shaped {field}")
    elif status == P0_STATUS_MERGED_PENDING_LIVE:
        merge_commit = data.get("migration_merge_commit")
        if not isinstance(merge_commit, str) or not _MERGE_COMMIT_SHA_RE.match(merge_commit.strip()):
            violations.append("merged_pending_live requires SHA-shaped migration_merge_commit")
        if not data.get("migration_applied_at_utc"):
            violations.append("merged_pending_live requires migration_applied_at_utc")
    elif status == P0_STATUS_LOCAL_ONLY:
        if data.get("migration_merge_commit"):
            violations.append("local_only must not set migration_merge_commit")
        if data.get("migration_applied_at_utc"):
            violations.append("local_only must not set migration_applied_at_utc")

    return violations


def validate_roadmap_p0_phrase(roadmap_text: str, p0_status: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    overall = str(p0_status.get("overall_status") or "")
    p0_row = re.search(
        r"^\|\s*\*\*P0\*\*\s*\|[^\n|]*\|([^\n|]+)\|\s*$",
        roadmap_text,
        re.MULTILINE,
    )
    if not p0_row:
        violations.append("issue_93_roadmap.md: P0 correction table row not found")
        return violations
    cell = p0_row.group(1).strip()
    if overall == P0_STATUS_CLOSED:
        for marker in _P0_ROADMAP_IN_PROGRESS_MARKERS:
            if marker in cell:
                violations.append(
                    f"roadmap P0 must not claim in-progress when p0 status is closed: {cell!r}"
                )
                break
        if "完了" not in cell and "closed" not in cell.lower():
            violations.append(f"roadmap P0 should indicate completion when closed: {cell!r}")
    else:
        if re.search(r"\b完了\b|\bclosed\b", cell, re.IGNORECASE):
            violations.append(
                f"roadmap P0 must not claim completion while overall_status is {overall!r}: {cell!r}"
            )
    return violations
