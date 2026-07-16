"""Pure validation for Issue #93 P1 hardening status SSOT."""
from __future__ import annotations

import re
from typing import Any

P1_STATUS_PLANNED = "planned"
P1_STATUS_LOCAL_ONLY = "local_only"
P1_STATUS_MERGED_PENDING_LIVE = "merged_pending_live"
P1_STATUS_CLOSED = "closed"

_TERMINAL = frozenset({P1_STATUS_CLOSED})
_NON_TERMINAL = frozenset({P1_STATUS_PLANNED, P1_STATUS_LOCAL_ONLY, P1_STATUS_MERGED_PENDING_LIVE})

_EVIDENCE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_MERGE_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)

_P1_ROADMAP_IN_PROGRESS_MARKERS = (
    "未完了",
    "着手前",
    "未実施",
    "in_progress",
    "pending",
    "local_only",
    "merged_pending_live",
    "未達",
    "未マージ",
)

_FORBIDDEN_P0_KEYS = ("migration_merge_commit", "migration_applied_at_utc")

_REQUIRED_CLOSED_SCALAR_FIELDS = (
    "p1_final_merge_commit",
    "stale_running_before",
    "stale_running_after",
    "reconcile_applied_at_utc",
)

_REQUIRED_CLOSED_MERGE_FIELDS = tuple(f"pr_p1_{n}_merge_commit" for n in range(1, 6))

_REQUIRED_CLOSED_CI_URL_FIELDS = tuple(f"pr_p1_{n}_merge_ci_url" for n in range(1, 6))

_REQUIRED_MERGED_PENDING_MERGE_FIELDS = _REQUIRED_CLOSED_MERGE_FIELDS

_REQUIRED_MERGED_PENDING_CI_URL_FIELDS = _REQUIRED_CLOSED_CI_URL_FIELDS

_REQUIRED_CLOSED_URL_FIELDS = (
    "pytest_ci_run_url",
    "daily_live_run_url",
    "stale_reconcile_run_url",
)

_REQUIRED_CLOSED_PATH_FIELDS = (
    "stale_before_snapshot_ref",
    "stale_after_snapshot_ref",
    "observability_runbook_path",
)


def _validate_merge_and_ci_fields(data: dict[str, Any], violations: list[str], *, label: str) -> None:
    for field in _REQUIRED_CLOSED_MERGE_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not _MERGE_COMMIT_SHA_RE.match(value.strip()):
            violations.append(f"{label} requires SHA-shaped {field}")
    for field in _REQUIRED_CLOSED_CI_URL_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
            violations.append(f"{label} requires URL-shaped {field}")


def validate_p1_status_document(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for key in _FORBIDDEN_P0_KEYS:
        if key in data:
            violations.append(f"P1 SSOT must not use P0-only field {key!r}")

    status = str(data.get("overall_status") or "")
    if status not in _TERMINAL | _NON_TERMINAL:
        violations.append(
            f"overall_status must be one of {sorted(_TERMINAL | _NON_TERMINAL)!r}, got {status!r}"
        )
        return violations

    if status == P1_STATUS_CLOSED:
        for field in _REQUIRED_CLOSED_SCALAR_FIELDS:
            if data.get(field) in (None, ""):
                violations.append(f"overall_status closed requires {field}")
        _validate_merge_and_ci_fields(data, violations, label="overall_status closed")
        for field in _REQUIRED_CLOSED_URL_FIELDS:
            value = data.get(field)
            if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                violations.append(f"overall_status closed requires URL-shaped {field}")
        for field in _REQUIRED_CLOSED_PATH_FIELDS:
            if not isinstance(data.get(field), str) or not str(data.get(field)).strip():
                violations.append(f"overall_status closed requires path {field}")

        final = data.get("p1_final_merge_commit")
        if not isinstance(final, str) or not _MERGE_COMMIT_SHA_RE.match(final.strip()):
            violations.append("overall_status closed requires SHA-shaped p1_final_merge_commit")
        pr5 = data.get("pr_p1_5_merge_commit")
        if isinstance(final, str) and isinstance(pr5, str) and final.strip() != pr5.strip():
            violations.append("p1_final_merge_commit must equal pr_p1_5_merge_commit")

        before = data.get("stale_running_before")
        after = data.get("stale_running_after")
        try:
            before_n = int(before)  # type: ignore[arg-type]
            after_n = int(after)  # type: ignore[arg-type]
            if after_n >= before_n:
                violations.append("stale_running_after must be less than stale_running_before")
            if after_n != 0:
                violations.append("overall_status closed requires stale_running_after: 0")
        except (TypeError, ValueError):
            violations.append("stale_running_before/after must be integers when closed")

    elif status == P1_STATUS_MERGED_PENDING_LIVE:
        _validate_merge_and_ci_fields(data, violations, label="merged_pending_live")
        if data.get("p1_final_merge_commit"):
            violations.append("merged_pending_live must not set p1_final_merge_commit (closed only)")

    elif status == P1_STATUS_LOCAL_ONLY:
        if data.get("p1_final_merge_commit"):
            violations.append("local_only must not set p1_final_merge_commit")
        for field in _REQUIRED_CLOSED_MERGE_FIELDS + _REQUIRED_CLOSED_CI_URL_FIELDS:
            if data.get(field):
                violations.append(f"local_only must not set {field}")

    return violations


def validate_p1_roadmap_phrase(roadmap_text: str, p1_status: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    overall = str(p1_status.get("overall_status") or "")
    p1_row = re.search(
        r"^\|\s*\*\*P1\*\*\s*\|[^\n|]*\|([^\n|]+)\|\s*$",
        roadmap_text,
        re.MULTILINE,
    )
    if not p1_row:
        violations.append("issue_93_roadmap.md: P1 correction table row not found")
        return violations
    cell = p1_row.group(1).strip()
    if overall == P1_STATUS_CLOSED:
        for marker in _P1_ROADMAP_IN_PROGRESS_MARKERS:
            if marker in cell:
                violations.append(
                    f"roadmap P1 must not claim in-progress when p1 status is closed: {cell!r}"
                )
                break
        if "CLOSED" not in cell.upper() and "完了" not in cell:
            violations.append(f"roadmap P1 should indicate completion when closed: {cell!r}")
    else:
        if re.search(r"\bCLOSED\b|\b完了\b", cell, re.IGNORECASE):
            violations.append(
                f"roadmap P1 must not claim completion while overall_status is {overall!r}: {cell!r}"
            )

    roadmap_meta = p1_status.get("roadmap")
    if not isinstance(roadmap_meta, dict):
        violations.append("P1 SSOT must include roadmap.p1_status_phrase")
        return violations
    embedded = roadmap_meta.get("p1_status_phrase")
    if not isinstance(embedded, str) or not embedded.strip():
        violations.append("roadmap.p1_status_phrase must be a non-empty string")
    elif embedded.strip() != cell:
        violations.append(
            "roadmap.p1_status_phrase must match P1 roadmap cell "
            + f"(SSOT {embedded.strip()!r} vs roadmap {cell!r})"
        )
    return violations
