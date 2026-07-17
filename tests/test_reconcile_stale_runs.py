from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stockradar.jobs.reconcile_stale_runs import (
    STALE_DEGRADED_REASON,
    build_reconcile_patch,
    select_stale_running_rows,
)

_NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _row(
    *,
    workflow: str = "daily.yml",
    run_id: str = "r1",
    github_run_id: int = 1,
    started_at_utc: str = "2026-07-10T00:00:00+00:00",
    status: str = "running",
) -> dict[str, object]:
    return {
        "id": run_id,
        "workflow": workflow,
        "github_run_id": github_run_id,
        "status": status,
        "started_at_utc": started_at_utc,
    }


@pytest.mark.unit
def test_select_stale_running_rows_includes_old_running() -> None:
    rows = [_row(started_at_utc="2026-07-10T00:00:00+00:00")]
    stale = select_stale_running_rows(rows, stale_after_hours=48, now_utc=_NOW)
    assert len(stale) == 1


@pytest.mark.unit
def test_select_stale_running_rows_excludes_recent_running() -> None:
    rows = [_row(started_at_utc="2026-07-16T10:00:00+00:00")]
    stale = select_stale_running_rows(rows, stale_after_hours=48, now_utc=_NOW)
    assert stale == []


@pytest.mark.unit
def test_select_stale_running_rows_excludes_non_target_workflow() -> None:
    rows = [_row(workflow="supabase_security_smoketest.yml")]
    stale = select_stale_running_rows(rows, stale_after_hours=48, now_utc=_NOW)
    assert stale == []


@pytest.mark.unit
def test_select_stale_running_rows_excludes_terminal_status() -> None:
    rows = [_row(status="success")]
    stale = select_stale_running_rows(rows, stale_after_hours=48, now_utc=_NOW)
    assert stale == []


@pytest.mark.unit
def test_build_reconcile_patch_sets_failed_and_reason() -> None:
    patch = build_reconcile_patch(finished_at_utc=_NOW)
    assert patch["status"] == "failed"
    assert patch["degraded_reason"] == STALE_DEGRADED_REASON
    assert patch["finished_at_utc"].endswith("+00:00")
