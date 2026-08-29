"""Pure helpers for ADR-005 series_seed / series_repair / history_quality."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


def validate_series_repair_approver(
    *,
    approver_github_login: str,
    worker_github_actor: str,
) -> None:
    """Reject self-approval (ADR-005). Team membership is ops-configured separately."""
    a = str(approver_github_login or "").strip().lower()
    w = str(worker_github_actor or "").strip().lower()
    if not a:
        raise ValueError("approver_github_login required")
    if not w:
        raise ValueError("worker_github_actor required")
    if a == w:
        raise PermissionError("series_repair self-approval is forbidden")


@dataclass(frozen=True)
class HistoryQualityInput:
    release_month: str
    feature_start_release_month: str | None
    request_statuses: tuple[str, ...]
    has_committed_coordinates: bool = False


def aggregate_history_quality(inp: HistoryQualityInput) -> dict[str, Any]:
    """Aggregate request statuses into history_quality.json body (ADR-005)."""
    fs = inp.feature_start_release_month
    if fs is None or not str(fs).strip():
        return {
            "schema_version": 1,
            "tier": "not_applicable",
            "release_month": inp.release_month,
            "reason": "feature_start_unset",
        }
    month = str(inp.release_month).strip()
    if month < str(fs).strip():
        return {
            "schema_version": 1,
            "tier": "not_applicable",
            "release_month": month,
            "reason": "before_feature_start",
        }
    statuses = [str(s) for s in inp.request_statuses]
    if not statuses:
        return {
            "schema_version": 1,
            "tier": "blocked_backfill",
            "release_month": month,
            "reason": "missing_in_scope_requests",
        }
    if any(s == "blocked" for s in statuses):
        tier = "partial_backfill" if inp.has_committed_coordinates else "blocked_backfill"
        return {"schema_version": 1, "tier": tier, "release_month": month, "statuses": statuses}
    terminal_ok = {"completed", "noop", "grandfather"}
    if all(s in terminal_ok for s in statuses):
        return {"schema_version": 1, "tier": "full", "release_month": month, "statuses": statuses}
    return {
        "schema_version": 1,
        "tier": "partial_backfill",
        "release_month": month,
        "statuses": statuses,
    }


def series_only_expected_object_count(touched_series_coordinate_count: int) -> int:
    n = int(touched_series_coordinate_count)
    if n < 0:
        raise ValueError("touched_series_coordinate_count must be >= 0")
    if n == 0:
        return 0
    return (2 * n) + 1


def classify_seed_trade_date_codes(
    *,
    candidate_codes: Sequence[str],
    existing_dates_by_code: Mapping[str, Iterable[str]],
    trade_date: str,
) -> dict[str, list[str]]:
    write: list[str] = []
    noop: list[str] = []
    for code in candidate_codes:
        c = str(code).strip()
        if not c:
            continue
        existing = {str(d) for d in existing_dates_by_code.get(c, [])}
        if trade_date in existing:
            noop.append(c)
        else:
            write.append(c)
    return {"write": write, "resolved_noop": noop}
