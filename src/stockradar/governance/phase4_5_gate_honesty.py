"""Pure validation for Phase 4.5 gate status vs operational docs."""
from __future__ import annotations

import re
from typing import Any

from stockradar.governance.phase_gate_honesty import (
    OVERALL_CLOSED,
    OVERALL_IN_PROGRESS,
    PR_GATE_NON_TERMINAL,
    PR_GATE_TERMINAL,
    _EVIDENCE_URL_RE,
    _MERGE_COMMIT_SHA_RE,
    _validate_merged_pr_ci_evidence,
)

_PHASE45_ROW_RE = re.compile(
    r"^\|\s*4\.5\s*\|[^\n|]*\|([^\n]+)\|\s*$",
    re.MULTILINE,
)
_CLOSED_PHRASE_FORBIDDEN_MARKERS = ("未マージ", "live gate 未達", "未達", "in_progress")
_FORBIDDEN_PHASE45_IF_NOT_CLOSED = (
    re.compile(r"gate\s+CLOSED", re.IGNORECASE),
    re.compile(r"\*\*" + "\u5b8c\u4e86" + r"\*\*"),
    re.compile(r"\*\*CLOSED\*\*", re.IGNORECASE),
)

REQUIRED_PR_GATE_IDS_V1: frozenset[str] = frozenset(
    {
        "pr-45-0-gate-ssot",
        "pr-45-0b-put-fixed",
        "pr-45-0c-layer1-poc",
        "pr-45-0d-budget",
        "pr-45-0e-registry",
    }
)

REQUIRED_PR_GATE_IDS: frozenset[str] = frozenset(
    {
        "pr-45-1",
        "pr-45-2",
        "pr-45-3",
        "pr-45-4",
    }
)

REQUIRED_HISTORICAL_PR_GATE_IDS: frozenset[str] = REQUIRED_PR_GATE_IDS_V1

REQUIRED_PREFLIGHT_BLOCKER_IDS: frozenset[str] = frozenset(
    {
        "layer1_5y_feasibility",
        "put_fixed_defect",
        "metric_registry_ddl",
        "supabase_r2_budget_fixture",
        "gate_ssot_and_rollout",
    }
)

VALID_ROLLOUT_STAGES: frozenset[str] = frozenset({"off", "4.5a", "4.5b", "4.5c"})
_ROLLOUT_STAGE_ORDER: tuple[str, ...] = ("off", "4.5a", "4.5b", "4.5c")

_EVIDENCE_REPO_PATH_RE = re.compile(
    r"^docs/operations/evidence/[a-z0-9_./-]+\.(json|md|yaml|yml)$",
    re.IGNORECASE,
)
_EVIDENCE_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)

_LIVE_GATE_45C_EVIDENCE_KEYS: tuple[str, ...] = (
    "normal_daily_success_run_url",
    "replay_no_shared_mutation_run_url",
    "backfill_shadow_only_run_url",
    "reconcile_isolated_run_url",
)

_USER_GATE_RULES: dict[str, tuple[tuple[str, bool], ...]] = {
    "pr-45-0d-budget": (("postgres_measurement_evidence_url", False),),
}


def _is_verifiable_evidence_ref(value: str) -> bool:
    stripped = value.strip()
    return bool(_EVIDENCE_URL_RE.match(stripped) or _EVIDENCE_REPO_PATH_RE.match(stripped))


def _validate_merged_pr_gate(gate_id: str, gate: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    violations.extend(_validate_merged_pr_ci_evidence(gate_id, gate))
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


def _validate_preflight_blocker(blocker_id: str, blocker: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    status = str(blocker.get("status") or "")
    if status not in {"open", "closed"}:
        violations.append(f"preflight_blockers.{blocker_id}.status must be open or closed")
        return violations
    if status == "closed":
        if not blocker.get("closed_at_utc"):
            violations.append(f"preflight_blockers.{blocker_id}: closed requires closed_at_utc")
        digest = blocker.get("evidence_digest")
        if not isinstance(digest, str) or not _EVIDENCE_DIGEST_RE.match(digest.strip()):
            violations.append(
                f"preflight_blockers.{blocker_id}: closed requires SHA256-shaped evidence_digest"
            )
        evidence_url = blocker.get("evidence_url")
        if not isinstance(evidence_url, str) or not _is_verifiable_evidence_ref(evidence_url):
            violations.append(
                f"preflight_blockers.{blocker_id}: closed requires "
                "URL- or repo-path-shaped evidence_url"
            )
        if blocker_id == "supabase_r2_budget_fixture":
            pg_url = blocker.get("postgres_measurement_evidence_url")
            if not isinstance(pg_url, str) or not _EVIDENCE_URL_RE.match(pg_url.strip()):
                violations.append(
                    f"preflight_blockers.{blocker_id}: closed requires "
                    "URL-shaped postgres_measurement_evidence_url"
                )
    return violations


def _validate_rollout(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    rollout = data.get("rollout")
    if not isinstance(rollout, dict):
        violations.append("rollout must be a mapping")
        return violations
    stage = str(rollout.get("current_stage") or "")
    if stage not in VALID_ROLLOUT_STAGES:
        violations.append(f"rollout.current_stage invalid: {stage!r}")
    history = rollout.get("stage_history")
    if history is not None and not isinstance(history, list):
        violations.append("rollout.stage_history must be a list when present")
    return violations


def _validate_capacity_gate(capacity: dict[str, Any], *, require_closed: bool) -> list[str]:
    violations: list[str] = []
    status = str(capacity.get("status") or "")
    if status not in {"open", "closed"}:
        violations.append("capacity_gate.status must be open or closed")
        return violations
    if require_closed or status == "closed":
        path = capacity.get("path")
        if path not in {"A", "B"}:
            violations.append("capacity_gate closed requires path A or B")
        catalog = capacity.get("catalog")
        if not isinstance(catalog, str) or not catalog:
            violations.append("capacity_gate closed requires catalog")
        if not isinstance(capacity.get("projection_inputs"), dict):
            violations.append("capacity_gate closed requires projection_inputs mapping")
        digest = capacity.get("evidence_report_hash")
        if not isinstance(digest, str) or not _EVIDENCE_DIGEST_RE.match(digest.strip()):
            violations.append("capacity_gate closed requires SHA256-shaped evidence_report_hash")
        evidence_url = capacity.get("evidence_url")
        if not isinstance(evidence_url, str) or not _is_verifiable_evidence_ref(evidence_url):
            violations.append("capacity_gate closed requires verifiable evidence_url")
    return violations


def validate_gate_status_document(data: dict[str, Any]) -> list[str]:
    """Return human-readable contract violations (empty if OK)."""
    violations: list[str] = []

    schema_version = data.get("schema_version")
    if schema_version == 1:
        return _validate_gate_status_document_v1(data)
    if schema_version != 2:
        violations.append("schema_version must be 1 (legacy) or 2")
        return violations
    return _validate_gate_status_document_v2(data)


def _validate_gate_status_document_v1(data: dict[str, Any]) -> list[str]:
    """Legacy schema v1 validation (preflight era)."""
    violations: list[str] = []
    old_required = REQUIRED_PR_GATE_IDS_V1

    overall = str(data.get("overall_status") or "")
    if overall not in {OVERALL_CLOSED, OVERALL_IN_PROGRESS}:
        violations.append(f"overall_status must be {OVERALL_IN_PROGRESS!r} or {OVERALL_CLOSED!r}")

    violations.extend(_validate_rollout(data))

    preflight = data.get("preflight_blockers")
    if not isinstance(preflight, dict):
        violations.append("preflight_blockers must be a mapping")
    else:
        missing = REQUIRED_PREFLIGHT_BLOCKER_IDS - set(preflight)
        if missing:
            violations.append(f"preflight_blockers missing ids: {sorted(missing)}")
        for blocker_id, blocker in preflight.items():
            if isinstance(blocker, dict):
                violations.extend(_validate_preflight_blocker(blocker_id, blocker))

    pr_gates = data.get("pr_gates")
    if not isinstance(pr_gates, dict) or not pr_gates:
        violations.append("pr_gates must be a non-empty mapping")
        return violations

    missing_gates = old_required - set(pr_gates)
    if missing_gates:
        violations.append(f"pr_gates missing required gate ids: {sorted(missing_gates)}")

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
            violations.extend(_validate_merged_pr_gate(gate_id, gate))

    live = data.get("live_gate_45c")
    live_status = ""
    if not isinstance(live, dict):
        violations.append("live_gate_45c must be a mapping")
    else:
        live_status = str(live.get("status") or "")
        if live_status not in {"open", "closed"}:
            violations.append("live_gate_45c.status must be open or closed")
        elif live_status == "closed":
            for key in _LIVE_GATE_45C_EVIDENCE_KEYS:
                value = live.get(key)
                if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                    violations.append(f"live_gate_45c closed requires URL-shaped {key}")
            if not live.get("closed_at_utc"):
                violations.append("live_gate_45c closed requires closed_at_utc")

    all_merged = all(
        isinstance(g, dict) and g.get("status") == "merged_and_verified" for g in pr_gates.values()
    )
    all_preflight_closed = isinstance(preflight, dict) and all(
        isinstance(b, dict) and b.get("status") == "closed" for b in preflight.values()
    )

    if overall == OVERALL_CLOSED:
        roadmap = data.get("roadmap")
        if isinstance(roadmap, dict):
            phrase = str(roadmap.get("phase45_status_phrase") or "")
            for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
                if marker in phrase:
                    violations.append(
                        "overall_status closed but roadmap.phase45_status_phrase "
                        f"still indicates in-progress: {phrase!r}"
                    )
                    break
        if not all_merged:
            violations.append("overall_status closed requires all pr_gates merged_and_verified")
        if not all_preflight_closed:
            violations.append("overall_status closed requires all preflight_blockers closed")
        if isinstance(live, dict) and live.get("status") != "closed":
            violations.append("overall_status closed requires live_gate_45c closed")
    elif all_merged and all_preflight_closed and live_status == "closed":
        violations.append(
            "overall_status must be closed when all pr_gates merged, "
            "preflight_blockers closed, and live_gate_45c closed"
        )

    gate_ssot = preflight.get("gate_ssot_and_rollout") if isinstance(preflight, dict) else None
    pr_45_0 = pr_gates.get("pr-45-0-gate-ssot")
    if isinstance(gate_ssot, dict) and isinstance(pr_45_0, dict):
        if gate_ssot.get("status") == "closed" and pr_45_0.get("status") != "merged_and_verified":
            violations.append(
                "preflight_blockers.gate_ssot_and_rollout closed requires "
                "pr-45-0-gate-ssot merged_and_verified"
            )

    return violations


def _validate_gate_status_document_v2(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    overall = str(data.get("overall_status") or "")
    if overall not in {OVERALL_CLOSED, OVERALL_IN_PROGRESS}:
        violations.append(f"overall_status must be {OVERALL_IN_PROGRESS!r} or {OVERALL_CLOSED!r}")

    violations.extend(_validate_rollout(data))

    preflight = data.get("preflight_blockers")
    if not isinstance(preflight, dict):
        violations.append("preflight_blockers must be a mapping")
    else:
        missing = REQUIRED_PREFLIGHT_BLOCKER_IDS - set(preflight)
        if missing:
            violations.append(f"preflight_blockers missing ids: {sorted(missing)}")
        for blocker_id, blocker in preflight.items():
            if isinstance(blocker, dict):
                violations.extend(_validate_preflight_blocker(blocker_id, blocker))

    historical = data.get("historical_pr_gates")
    if not isinstance(historical, dict):
        violations.append("historical_pr_gates must be a mapping for schema v2")
    else:
        missing_hist = REQUIRED_HISTORICAL_PR_GATE_IDS - set(historical)
        if missing_hist:
            violations.append(
                f"historical_pr_gates missing required gate ids: {sorted(missing_hist)}"
            )
        for gate_id, gate in historical.items():
            if not isinstance(gate, dict):
                violations.append(f"historical_pr_gates.{gate_id} must be a mapping")
                continue
            status = str(gate.get("status") or "")
            if status == "merged_and_verified":
                merge_commit = gate.get("merge_commit")
                if not isinstance(merge_commit, str) or not _MERGE_COMMIT_SHA_RE.match(
                    merge_commit.strip()
                ):
                    violations.append(
                        f"historical_pr_gates.{gate_id}: merged_and_verified requires "
                        "SHA-shaped merge_commit"
                    )
                violations.extend(_validate_merged_pr_gate(gate_id, gate))

    pr_gates = data.get("pr_gates")
    if not isinstance(pr_gates, dict) or not pr_gates:
        violations.append("pr_gates must be a non-empty mapping")
        return violations

    missing_gates = REQUIRED_PR_GATE_IDS - set(pr_gates)
    if missing_gates:
        violations.append(f"pr_gates missing required gate ids: {sorted(missing_gates)}")

    duplicate_historical = REQUIRED_PR_GATE_IDS & set(historical or {})
    if duplicate_historical:
        violations.append(
            f"historical_pr_gates must not duplicate active pr gate ids: {sorted(duplicate_historical)}"
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
            violations.extend(_validate_merged_pr_gate(gate_id, gate))

    capacity = data.get("capacity_gate")
    if not isinstance(capacity, dict):
        violations.append("capacity_gate must be a mapping for schema v2")
    else:
        violations.extend(_validate_capacity_gate(capacity, require_closed=overall == OVERALL_CLOSED))

    live = data.get("live_gate_45c")
    live_status = ""
    if not isinstance(live, dict):
        violations.append("live_gate_45c must be a mapping")
    else:
        live_status = str(live.get("status") or "")
        if live_status not in {"open", "closed"}:
            violations.append("live_gate_45c.status must be open or closed")
        elif live_status == "closed":
            for key in _LIVE_GATE_45C_EVIDENCE_KEYS:
                value = live.get(key)
                if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
                    violations.append(f"live_gate_45c closed requires URL-shaped {key}")
            soak = live.get("soak_run_urls")
            if not isinstance(soak, list) or len(soak) < 3:
                violations.append("live_gate_45c closed requires soak_run_urls length >= 3")
            if not live.get("closed_at_utc"):
                violations.append("live_gate_45c closed requires closed_at_utc")

    all_merged = all(
        isinstance(g, dict) and g.get("status") == "merged_and_verified" for g in pr_gates.values()
    )
    all_preflight_closed = isinstance(preflight, dict) and all(
        isinstance(b, dict) and b.get("status") == "closed" for b in preflight.values()
    )
    capacity_closed = isinstance(capacity, dict) and capacity.get("status") == "closed"

    if overall == OVERALL_CLOSED:
        roadmap = data.get("roadmap")
        if isinstance(roadmap, dict):
            phrase = str(roadmap.get("phase45_status_phrase") or "")
            for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
                if marker in phrase:
                    violations.append(
                        "overall_status closed but roadmap.phase45_status_phrase "
                        f"still indicates in-progress: {phrase!r}"
                    )
                    break
        if not all_merged:
            violations.append("overall_status closed requires all pr_gates merged_and_verified")
        if not all_preflight_closed:
            violations.append("overall_status closed requires all preflight_blockers closed")
        if not capacity_closed:
            violations.append("overall_status closed requires capacity_gate closed")
        if isinstance(live, dict) and live.get("status") != "closed":
            violations.append("overall_status closed requires live_gate_45c closed")
    elif all_merged and all_preflight_closed and capacity_closed and live_status == "closed":
        violations.append(
            "overall_status must be closed when all pr_gates merged, "
            "preflight_blockers closed, capacity_gate closed, and live_gate_45c closed"
        )

    gate_ssot = preflight.get("gate_ssot_and_rollout") if isinstance(preflight, dict) else None
    historical = data.get("historical_pr_gates")
    pr_45_0 = historical.get("pr-45-0-gate-ssot") if isinstance(historical, dict) else None
    if isinstance(gate_ssot, dict) and isinstance(pr_45_0, dict):
        if gate_ssot.get("status") == "closed" and pr_45_0.get("status") != "merged_and_verified":
            violations.append(
                "preflight_blockers.gate_ssot_and_rollout closed requires "
                "historical_pr_gates.pr-45-0-gate-ssot merged_and_verified"
            )

    return violations


def validate_gate_status_document_legacy(data: dict[str, Any]) -> list[str]:
    """Backward-compatible alias."""
    return validate_gate_status_document(data)


def _normalize_roadmap_status_cell(cell: str) -> str:
    return re.sub(r"\*\*", "", cell).strip()


def extract_phase45_roadmap_phrase(roadmap_text: str) -> str | None:
    match = _PHASE45_ROW_RE.search(roadmap_text)
    if not match:
        return None
    return match.group(1).strip()


def validate_roadmap_against_gate_status(
    roadmap_text: str,
    gate_status: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    status_cell = extract_phase45_roadmap_phrase(roadmap_text)
    if status_cell is None:
        violations.append("issue_93_roadmap.md: Phase 4.5 table row not found")
        return violations

    expected = gate_status.get("roadmap")
    if isinstance(expected, dict):
        expected_phrase = str(expected.get("phase45_status_phrase") or "")
        normalized_cell = _normalize_roadmap_status_cell(status_cell)
        if expected_phrase and normalized_cell != expected_phrase:
            violations.append(
                f"roadmap Phase 4.5 phrase {normalized_cell!r} != "
                f"gate_status roadmap.phase45_status_phrase {expected_phrase!r}"
            )

    overall = str(gate_status.get("overall_status") or "")
    if overall == OVERALL_CLOSED:
        for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
            if marker in status_cell:
                violations.append(
                    f"roadmap Phase 4.5 must not claim in-progress when overall_status is closed: "
                    f"{status_cell!r}"
                )
                break
    elif overall != OVERALL_CLOSED:
        for pattern in _FORBIDDEN_PHASE45_IF_NOT_CLOSED:
            if pattern.search(status_cell):
                violations.append(
                    f"roadmap Phase 4.5 must not claim completion while overall_status is "
                    f"{overall!r}: {status_cell!r}"
                )
                break

    return violations
