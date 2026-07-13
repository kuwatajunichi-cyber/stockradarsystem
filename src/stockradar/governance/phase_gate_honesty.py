"""Pure validation for phase gate status vs operational docs."""
from __future__ import annotations

import re
from typing import Any

PR_GATE_TERMINAL = frozenset({"merged_and_verified"})
PR_GATE_NON_TERMINAL = frozenset({"pending", "local_only"})
OVERALL_CLOSED = "closed"
OVERALL_IN_PROGRESS = "in_progress"

_PHASE4_ROW_RE = re.compile(
    r"^\|\s*4\s*\|[^\n|]*\|([^\n]+)\|\s*$",
    re.MULTILINE,
)
_EVIDENCE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_MERGE_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_CLOSED_PHRASE_FORBIDDEN_MARKERS = ("未マージ", "live gate 未達", "未達", "in_progress")

_FORBIDDEN_PHASE4_IF_NOT_CLOSED = (
    re.compile(r"gate\s+CLOSED", re.IGNORECASE),
    re.compile(r"\*\*" + "\u5b8c\u4e86" + r"\*\*"),
    re.compile(r"\*\*CLOSED\*\*", re.IGNORECASE),
)



REQUIRED_PR_GATE_IDS: frozenset[str] = frozenset(
    {
        "pr-4-1-ddl",
        "pr-4-2-monthly-shadow",
        "pr-4-3-resolve-4b",
        "pr-4-4-publish-runs",
        "pr-4-5-jpx-url",
        "pr-4-6a-worker",
        "pr-4-6b-cutover",
    }
)

_USER_GATE_RULES: dict[str, tuple[tuple[str, bool], ...]] = {
    "pr-4-1-ddl": (("u1_ddl_applied", True), ("u1_evidence_url", False)),
    "pr-4-3-resolve-4b": (("live_gate_4b_evidence_url", False),),
    "pr-4-6b-cutover": (("u3_wrangler_deploy_evidence_url", False),),
}


def _validate_merged_pr_gate(gate_id: str, gate: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for field, must_be_true in _USER_GATE_RULES.get(gate_id, ()):
        value = gate.get(field)
        if must_be_true:
            if value is not True:
                violations.append(f"pr_gates.{gate_id}: merged_and_verified requires {field}: true")
        elif field.endswith("_url"):
            if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                violations.append(
                    f"pr_gates.{gate_id}: merged_and_verified requires URL-shaped {field}"
                )
        elif not value:
            violations.append(f"pr_gates.{gate_id}: merged_and_verified requires {field}")
    return violations

def validate_gate_status_document(data: dict[str, Any]) -> list[str]:
    """Return human-readable contract violations (empty if OK)."""
    violations: list[str] = []

    overall = str(data.get("overall_status") or "")
    if overall not in {OVERALL_CLOSED, OVERALL_IN_PROGRESS}:
        violations.append(f"overall_status must be {OVERALL_IN_PROGRESS!r} or {OVERALL_CLOSED!r}")

    pr_gates = data.get("pr_gates")
    if not isinstance(pr_gates, dict) or not pr_gates:
        violations.append("pr_gates must be a non-empty mapping")
        return violations

    missing_gates = REQUIRED_PR_GATE_IDS - set(pr_gates)
    if missing_gates:
        violations.append(
            f"pr_gates missing required gate ids: {sorted(missing_gates)}"
        )

    for gate_id, gate in pr_gates.items():
        if not isinstance(gate, dict):
            violations.append(f"pr_gates.{gate_id} must be a mapping")
            continue
        status = str(gate.get("status") or "")
        allowed = PR_GATE_TERMINAL | PR_GATE_NON_TERMINAL
        if status not in allowed:
            violations.append(f"pr_gates.{gate_id}.status invalid: {status!r}")
            continue
        if status == "merged_and_verified":
            merge_commit = gate.get("merge_commit")
            if not isinstance(merge_commit, str) or not _MERGE_COMMIT_SHA_RE.match(merge_commit.strip()):
                violations.append(f"pr_gates.{gate_id}: merged_and_verified requires SHA-shaped merge_commit")
            if gate.get("pytest_ci_pass_on_merge") is not True:
                violations.append(
                    f"pr_gates.{gate_id}: merged_and_verified requires pytest_ci_pass_on_merge: true"
                )
            violations.extend(_validate_merged_pr_gate(gate_id, gate))

    live = data.get("live_gate_4c")
    if not isinstance(live, dict):
        violations.append("live_gate_4c must be a mapping")
        return violations

    live_status = str(live.get("status") or "")
    if live_status not in {"open", "closed"}:
        violations.append("live_gate_4c.status must be open or closed")

    evidence_keys = (
        "release_removed_daily_success_run_url",
        "publish_status_committed_run_url",
        "runs_status_run_url",
        "cron_dispatch_run_url",
    )
    if live_status == "closed":
        for key in evidence_keys:
            value = live.get(key)
            if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                violations.append(f"live_gate_4c closed requires URL-shaped {key}")
        if not live.get("closed_at_utc"):
            violations.append("live_gate_4c closed requires closed_at_utc")

    all_merged = all(
        isinstance(g, dict) and g.get("status") == "merged_and_verified" for g in pr_gates.values()
    )
    if overall == OVERALL_CLOSED:
        roadmap = data.get("roadmap")
        if isinstance(roadmap, dict):
            phrase = str(roadmap.get("phase4_status_phrase") or "")
            for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
                if marker in phrase:
                    violations.append(
                        f"overall_status closed but roadmap.phase4_status_phrase still indicates in-progress: {phrase!r}"
                    )
                    break
        if not all_merged:
            violations.append("overall_status closed requires all pr_gates merged_and_verified")
        if live_status != "closed":
            violations.append("overall_status closed requires live_gate_4c closed")
    else:
        if all_merged and live_status == "closed":
            violations.append(
                "overall_status must be closed when all pr_gates merged and live_gate_4c closed"
            )

    return violations


def _normalize_roadmap_status_cell(cell: str) -> str:
    return re.sub(r"\*\*", "", cell).strip()


def extract_phase4_roadmap_phrase(roadmap_text: str) -> str | None:
    match = _PHASE4_ROW_RE.search(roadmap_text)
    if not match:
        return None
    return match.group(1).strip()


def validate_roadmap_against_gate_status(
    roadmap_text: str,
    gate_status: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    status_cell = extract_phase4_roadmap_phrase(roadmap_text)
    if status_cell is None:
        violations.append("issue_93_roadmap.md: Phase 4 table row not found")
        return violations

    expected = gate_status.get("roadmap")
    if isinstance(expected, dict):
        expected_phrase = str(expected.get("phase4_status_phrase") or "")
        normalized_cell = _normalize_roadmap_status_cell(status_cell)
        if expected_phrase and normalized_cell != expected_phrase:
            violations.append(
                f"roadmap Phase 4 phrase {normalized_cell!r} != gate_status roadmap.phase4_status_phrase "
                f"{expected_phrase!r}"
            )

    overall = str(gate_status.get("overall_status") or "")
    if overall == OVERALL_CLOSED:
        for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
            if marker in status_cell:
                violations.append(
                    f"roadmap Phase 4 must not claim in-progress when overall_status is closed: {status_cell!r}"
                )
                break
    elif overall != OVERALL_CLOSED:
        for pattern in _FORBIDDEN_PHASE4_IF_NOT_CLOSED:
            if pattern.search(status_cell):
                violations.append(
                    f"roadmap Phase 4 must not claim completion while overall_status is "
                    f"{overall!r}: {status_cell!r}"
                )
                break
        if "\u672a" not in status_cell and "in_progress" not in status_cell.lower():
            violations.append(
                f"roadmap Phase 4 should explicitly indicate not closed: {status_cell!r}"
            )

    return violations
