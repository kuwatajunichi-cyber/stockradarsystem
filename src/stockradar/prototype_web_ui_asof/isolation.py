"""P-ISO isolation helpers for the as-of prototype."""
from __future__ import annotations

from pathlib import Path

from stockradar.prototype_web_ui_asof import (
    FORBIDDEN_FREEZE_IMPORT_SUBSTRINGS,
    P_ISO_README_MARKERS,
)

ALLOWED_BIND_HOSTS = frozenset({"127.0.0.1"})


def validate_bind_host(host: str) -> None:
    if host not in ALLOWED_BIND_HOSTS:
        raise ValueError(f"bind host must be 127.0.0.1 only, got {host!r}")


def validate_readme_markers(text: str) -> list[str]:
    missing = [m for m in P_ISO_README_MARKERS if m not in text]
    return [f"prototype README missing marker {m!r}" for m in missing]


def scan_source_for_forbidden_imports(source: str) -> list[str]:
    hits: list[str] = []
    lowered = source.lower()
    for token in FORBIDDEN_FREEZE_IMPORT_SUBSTRINGS:
        if token.lower() in lowered:
            hits.append(f"forbidden import/token present: {token}")
    return hits


def assert_gate_track_d_still_open(gate_status: dict) -> list[str]:
    violations: list[str] = []
    tracks = gate_status.get("tracks") or {}
    d = tracks.get("D_web_ui") or tracks.get("D") or {}
    if str(d.get("status") or "").lower() in {"closed", "merged_and_verified"}:
        violations.append("Track D must remain pending for prototype work")
    pr = (gate_status.get("pr_gates") or {}).get("pr-5d-web-ui") or {}
    if str(pr.get("status") or "").lower() == "merged_and_verified":
        violations.append("pr-5d-web-ui must not be closed by prototype")
    live = (gate_status.get("live_gates") or {}).get("live_gate_5d") or {}
    if str(live.get("status") or "").lower() == "closed":
        violations.append("live_gate_5d must stay open for prototype")
    overall = str(gate_status.get("overall_status") or "")
    if overall == "closed":
        violations.append("Phase 5 overall_status must not be closed by prototype")
    return violations


def read_package_source_tree(pkg_dir: Path) -> str:
    parts: list[str] = []
    for path in sorted(pkg_dir.glob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
