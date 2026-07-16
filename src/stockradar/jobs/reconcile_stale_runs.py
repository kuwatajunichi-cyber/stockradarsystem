"""Pure stale running run selection and reconcile patch (Issue #93 P1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_STALE_WORKFLOWS: tuple[str, ...] = (
    "daily.yml",
    "monthly.yml",
    "daily_universe_patch.yml",
    "daily_event_cause_enrichment.yml",
    "supabase_smoketest.yml",
)

STALE_DEGRADED_REASON = "stale_running_reconciled"


def parse_started_at_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def select_stale_running_rows(
    rows: list[dict[str, Any]],
    *,
    stale_after_hours: float,
    now_utc: datetime,
    allowed_workflows: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    cutoff = now_utc - timedelta(hours=stale_after_hours)
    workflows = allowed_workflows or frozenset(DEFAULT_STALE_WORKFLOWS)
    stale: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "") != "running":
            continue
        workflow = str(row.get("workflow") or "")
        if workflow not in workflows:
            continue
        started_raw = row.get("started_at_utc")
        if not isinstance(started_raw, str) or not started_raw.strip():
            continue
        started = parse_started_at_utc(started_raw)
        if started < cutoff:
            stale.append(dict(row))
    stale.sort(key=lambda r: (str(r.get("workflow") or ""), int(r.get("github_run_id") or 0)))
    return stale


def build_reconcile_patch(*, finished_at_utc: datetime) -> dict[str, str]:
    if finished_at_utc.tzinfo is None:
        finished_at_utc = finished_at_utc.replace(tzinfo=timezone.utc)
    return {
        "status": "failed",
        "finished_at_utc": finished_at_utc.isoformat(),
        "degraded_reason": STALE_DEGRADED_REASON,
    }
