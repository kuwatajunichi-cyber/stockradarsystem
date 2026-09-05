"""Pure validation for Phase 5 gate status vs operational docs."""

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

_PHASE5_ROW_RE = re.compile(
    r"^\|\s*5\s*\|[^\n|]*\|([^\n]+)\|\s*$",
    re.MULTILINE,
)
_CLOSED_PHRASE_FORBIDDEN_MARKERS = (
    "未マージ",
    "live gate 未達",
    "未達",
    "in_progress",
    "未実装",
    "未着手",
)
_FORBIDDEN_PHASE5_IF_NOT_CLOSED = (
    re.compile(r"(?<![_\w])gate\s+CLOSED", re.IGNORECASE),
    re.compile(r"\*\*" + "\u5b8c\u4e86" + r"\*\*"),
    re.compile(r"\*\*CLOSED\*\*", re.IGNORECASE),
)

REQUIRED_PR_GATE_IDS: frozenset[str] = frozenset(
    {
        "pr-50-track-map",
        "pr-55a-healthchecks",
        "pr-55b-runs-views",
        "pr-5b-signed-capability",
        "pr-5c-auth-entitlements",
        "pr-5d-web-ui",
        "pr-5e-distribution",
    }
)

REQUIRED_TRACK_IDS: frozenset[str] = frozenset(
    {
        "A_observability",
        "B_delivery_capability",
        "C_auth_entitlements",
        "D_web_ui",
        "E_distribution",
    }
)

REQUIRED_LIVE_GATE_IDS: frozenset[str] = frozenset(
    {
        "live_gate_55a",
        "live_gate_55b",
        "live_gate_5b",
        "live_gate_5c",
        "live_gate_5d",
        "live_gate_5e",
    }
)

REQUIRED_USER_GATE_IDS: frozenset[str] = frozenset({"u-55a-1", "u-55a-2"})

TRACK_STATUSES = frozenset({"pending", "in_progress", "closed"})
USER_GATE_STATUSES = frozenset({"pending", "completed"})
LIVE_GATE_STATUSES = frozenset({"open", "closed"})

_LIVE_GATE_55A_EVIDENCE_KEYS: tuple[str, ...] = (
    "patch_success_ping_run_url",
    "daily_success_ping_run_url",
    "skip_publish_no_ping_run_url",
    "replay_no_ping_run_url",
    "closed_day_expected_ping_run_url",
)

CALENDAR_POLICY_TOKEN = "closed_day_expected_ping"

_CUTOVER_REQUIRED_MARKERS: tuple[str, ...] = (
    CALENDAR_POLICY_TOKEN,
    "is_replay",
    "skip_publish",
    "Watchdog",
    "continue-on-error",
)

# Weekend false-Down if Period 1d + no ping on closed days.
_CUTOVER_FORBIDDEN_LIVE_CALENDAR: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\*\*休場日:\*\*[^\n]*is_open=False[^\n]*ping なし",
        re.IGNORECASE,
    ),
    re.compile(
        r"休場日:[^\n]*skip\s*→\s*ping なし",
        re.IGNORECASE,
    ),
)


def _normalize_roadmap_status_cell(cell: str) -> str:
    return re.sub(r"\*\*", "", cell).strip()


def extract_phase5_roadmap_phrase(roadmap_text: str) -> str | None:
    match = _PHASE5_ROW_RE.search(roadmap_text)
    if not match:
        return None
    return match.group(1).strip()


def _all_pr_gates_merged(pr_gates: dict[str, Any]) -> bool:
    return all(
        isinstance(g, dict) and g.get("status") == "merged_and_verified"
        for g in pr_gates.values()
    )


def _all_live_gates_closed(live_gates: dict[str, Any]) -> bool:
    return all(
        isinstance(g, dict) and g.get("status") == "closed" for g in live_gates.values()
    )


def _all_tracks_closed(tracks: dict[str, Any]) -> bool:
    return all(
        isinstance(t, dict) and t.get("status") == "closed" for t in tracks.values()
    )


def validate_cutover_calendar_contract(cutover_text: str) -> list[str]:
    """Cutover must adopt closed-day ping before Healthchecks Period 1d goes live."""
    violations: list[str] = []
    for marker in _CUTOVER_REQUIRED_MARKERS:
        if marker not in cutover_text:
            violations.append(
                f"phase5_observability_cutover.md missing required marker {marker!r}"
            )
    for pattern in _CUTOVER_FORBIDDEN_LIVE_CALENDAR:
        if pattern.search(cutover_text):
            violations.append(
                "phase5_observability_cutover.md must not keep Period 1d + closed-day "
                "no-ping as the live calendar policy"
            )
            break
    if "Period 1d × 閉場日非 ping" not in cutover_text and "毎週末" not in cutover_text:
        violations.append(
            "phase5_observability_cutover.md must document the weekend false-Down "
            "from Period 1d + closed-day no-ping"
        )
    return violations


def validate_gate_status_document(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    overall = str(data.get("overall_status") or "")
    if overall not in {OVERALL_CLOSED, OVERALL_IN_PROGRESS}:
        violations.append(
            f"overall_status must be {OVERALL_IN_PROGRESS!r} or {OVERALL_CLOSED!r}"
        )

    tracks = data.get("tracks")
    if not isinstance(tracks, dict) or not tracks:
        violations.append("tracks must be a non-empty mapping")
        return violations
    missing_tracks = REQUIRED_TRACK_IDS - set(tracks)
    if missing_tracks:
        violations.append(f"tracks missing required ids: {sorted(missing_tracks)}")
    for track_id, track in tracks.items():
        if not isinstance(track, dict):
            violations.append(f"tracks.{track_id} must be a mapping")
            continue
        status = str(track.get("status") or "")
        if status not in TRACK_STATUSES:
            violations.append(f"tracks.{track_id}.status invalid: {status!r}")

    pr_gates = data.get("pr_gates")
    if not isinstance(pr_gates, dict) or not pr_gates:
        violations.append("pr_gates must be a non-empty mapping")
        return violations
    missing_gates = REQUIRED_PR_GATE_IDS - set(pr_gates)
    if missing_gates:
        violations.append(
            f"pr_gates missing required gate ids: {sorted(missing_gates)}"
        )
    extra = set(pr_gates) - REQUIRED_PR_GATE_IDS
    if extra:
        violations.append(f"pr_gates has unexpected gate ids: {sorted(extra)}")

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
            if not isinstance(merge_commit, str) or not _MERGE_COMMIT_SHA_RE.match(
                merge_commit.strip()
            ):
                violations.append(
                    f"pr_gates.{gate_id}: merged_and_verified requires SHA-shaped merge_commit"
                )
            violations.extend(_validate_merged_pr_ci_evidence(gate_id, gate))
            if gate_id == "pr-55a-healthchecks":
                violations.extend(_validate_55a_user_gates_for_merge(data, gate_id))

    user_gates = data.get("user_gates")
    if not isinstance(user_gates, dict):
        violations.append("user_gates must be a mapping")
        user_gates = {}
    missing_users = REQUIRED_USER_GATE_IDS - set(user_gates)
    if missing_users:
        violations.append(f"user_gates missing required ids: {sorted(missing_users)}")
    for uid, ugate in user_gates.items():
        if not isinstance(ugate, dict):
            violations.append(f"user_gates.{uid} must be a mapping")
            continue
        ustatus = str(ugate.get("status") or "")
        if ustatus not in USER_GATE_STATUSES:
            violations.append(f"user_gates.{uid}.status invalid: {ustatus!r}")
        if ustatus == "completed":
            evidence = ugate.get("evidence_url")
            if not isinstance(evidence, str) or not _EVIDENCE_URL_RE.match(
                evidence.strip()
            ):
                violations.append(
                    f"user_gates.{uid}: completed requires URL-shaped evidence_url"
                )

    live_gates = data.get("live_gates")
    if not isinstance(live_gates, dict) or not live_gates:
        violations.append("live_gates must be a non-empty mapping")
        return violations
    missing_live = REQUIRED_LIVE_GATE_IDS - set(live_gates)
    if missing_live:
        violations.append(f"live_gates missing required ids: {sorted(missing_live)}")
    extra_live = set(live_gates) - REQUIRED_LIVE_GATE_IDS
    if extra_live:
        violations.append(f"live_gates has unexpected ids: {sorted(extra_live)}")

    for live_id, live in live_gates.items():
        if not isinstance(live, dict):
            violations.append(f"live_gates.{live_id} must be a mapping")
            continue
        live_status = str(live.get("status") or "")
        if live_status not in LIVE_GATE_STATUSES:
            violations.append(f"live_gates.{live_id}.status must be open or closed")
            continue
        if live_status == "closed":
            if not live.get("closed_at_utc"):
                violations.append(f"live_gates.{live_id} closed requires closed_at_utc")
            if live_id == "live_gate_55a":
                violations.extend(_validate_live_gate_55a_closed(data, live))

    all_merged = _all_pr_gates_merged(pr_gates)
    all_live_closed = _all_live_gates_closed(live_gates)
    all_tracks_done = _all_tracks_closed(tracks)

    if overall == OVERALL_CLOSED:
        roadmap = data.get("roadmap")
        if isinstance(roadmap, dict):
            phrase = str(roadmap.get("phase5_status_phrase") or "")
            for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
                if marker in phrase:
                    violations.append(
                        "overall_status closed but roadmap.phase5_status_phrase "
                        f"still indicates in-progress: {phrase!r}"
                    )
                    break
        if not all_merged:
            violations.append(
                "overall_status closed requires all pr_gates merged_and_verified"
            )
        if not all_live_closed:
            violations.append(
                "overall_status closed requires all live_gates closed "
                "(live_gate_55a alone is not enough)"
            )
        if not all_tracks_done:
            violations.append("overall_status closed requires all tracks closed")
    elif all_merged and all_live_closed and all_tracks_done:
        violations.append(
            "overall_status must be closed when all pr_gates merged, "
            "all live_gates closed, and all tracks closed"
        )

    live_55a = live_gates.get("live_gate_55a")
    if (
        overall == OVERALL_CLOSED
        and isinstance(live_55a, dict)
        and live_55a.get("status") == "closed"
        and not all_merged
    ):
        violations.append(
            "overall_status must stay in_progress when tracks other than 5.5a remain open"
        )

    return violations


def _validate_55a_user_gates_for_merge(data: dict[str, Any], gate_id: str) -> list[str]:
    violations: list[str] = []
    user_gates = data.get("user_gates")
    if not isinstance(user_gates, dict):
        violations.append(
            f"pr_gates.{gate_id}: merged_and_verified requires user_gates mapping"
        )
        return violations
    for uid in REQUIRED_USER_GATE_IDS:
        ugate = user_gates.get(uid)
        if not isinstance(ugate, dict) or ugate.get("status") != "completed":
            violations.append(
                f"pr_gates.{gate_id}: merged_and_verified requires user_gates.{uid} completed"
            )
    return violations


def _validate_live_gate_55a_closed(
    data: dict[str, Any], live: dict[str, Any]
) -> list[str]:
    violations: list[str] = []
    for key in _LIVE_GATE_55A_EVIDENCE_KEYS:
        value = live.get(key)
        if not isinstance(value, str) or not _EVIDENCE_URL_RE.match(value.strip()):
            violations.append(
                f"live_gates.live_gate_55a closed requires URL-shaped {key}"
            )
    user_gates = data.get("user_gates")
    if not isinstance(user_gates, dict):
        violations.append("live_gates.live_gate_55a closed requires user_gates mapping")
        return violations
    for uid in REQUIRED_USER_GATE_IDS:
        ugate = user_gates.get(uid)
        if not isinstance(ugate, dict) or ugate.get("status") != "completed":
            violations.append(
                f"live_gates.live_gate_55a closed requires user_gates.{uid} completed"
            )
        elif not isinstance(
            ugate.get("evidence_url"), str
        ) or not _EVIDENCE_URL_RE.match(str(ugate.get("evidence_url")).strip()):
            violations.append(
                f"live_gates.live_gate_55a closed requires URL-shaped user_gates.{uid}.evidence_url"
            )
    pr_55a = (
        data.get("pr_gates", {}).get("pr-55a-healthchecks")
        if isinstance(data.get("pr_gates"), dict)
        else None
    )
    if not isinstance(pr_55a, dict) or pr_55a.get("status") != "merged_and_verified":
        violations.append(
            "live_gates.live_gate_55a closed requires pr_gates.pr-55a-healthchecks "
            "merged_and_verified"
        )
    return violations


def validate_roadmap_against_gate_status(
    roadmap_text: str,
    gate_status: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    status_cell = extract_phase5_roadmap_phrase(roadmap_text)
    if status_cell is None:
        violations.append("issue_93_roadmap.md: Phase 5 table row not found")
        return violations

    expected = gate_status.get("roadmap")
    if isinstance(expected, dict):
        expected_phrase = str(expected.get("phase5_status_phrase") or "")
        normalized_cell = _normalize_roadmap_status_cell(status_cell)
        if expected_phrase and normalized_cell != expected_phrase:
            violations.append(
                f"roadmap Phase 5 phrase {normalized_cell!r} != "
                f"gate_status roadmap.phase5_status_phrase {expected_phrase!r}"
            )

    overall = str(gate_status.get("overall_status") or "")
    if overall == OVERALL_CLOSED:
        for marker in _CLOSED_PHRASE_FORBIDDEN_MARKERS:
            if marker in status_cell:
                violations.append(
                    "roadmap Phase 5 must not claim in-progress when overall_status is closed: "
                    f"{status_cell!r}"
                )
                break
    else:
        for pattern in _FORBIDDEN_PHASE5_IF_NOT_CLOSED:
            if pattern.search(status_cell):
                violations.append(
                    f"roadmap Phase 5 must not claim completion while overall_status is "
                    f"{overall!r}: {status_cell!r}"
                )
                break
        if "in_progress" not in status_cell.lower() and "\u672a" not in status_cell:
            violations.append(
                f"roadmap Phase 5 should explicitly indicate not closed: {status_cell!r}"
            )

    phase5_section = _phase5_section_body(roadmap_text)
    if "is_replay" not in phase5_section or "skip_publish" not in phase5_section:
        violations.append(
            "roadmap Phase 5 must keep is_replay / skip_publish as non-ping"
        )
    if "Watchdog" not in phase5_section:
        violations.append(
            "roadmap Phase 5 must state Watchdog is not a Healthchecks substitute"
        )
    if (
        "**OPEN**" not in roadmap_text
        and "OPEN" not in roadmap_text.split("## Phase 5")[0]
    ):
        violations.append(
            "roadmap must keep Issue #93 OPEN while Phase 5 is in_progress"
        )
    for track_label in (
        "トラック A",
        "トラック B",
        "トラック C",
        "トラック D",
        "トラック E",
    ):
        if track_label not in phase5_section:
            violations.append(f"roadmap Phase 5 must name {track_label}")
    if re.search(r"連続[^\n]*soak 達成(?!とは書かない)", phase5_section):
        violations.append("roadmap Phase 5 must not claim continuous soak achievement")
    if re.search(r"Web UI 完了(?!とは書かない)", phase5_section):
        violations.append("roadmap Phase 5 must not claim Web UI complete")
    return violations


def _phase5_section_body(roadmap_text: str) -> str:
    if "## Phase 5" not in roadmap_text:
        return ""
    rest = roadmap_text.split("## Phase 5", 1)[1]
    nxt = rest.find("\n## ")
    if nxt != -1:
        rest = rest[:nxt]
    return rest
