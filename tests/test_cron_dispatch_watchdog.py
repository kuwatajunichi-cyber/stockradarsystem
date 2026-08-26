"""Pure watchdog verdicts for Cloudflare Cron dispatch misses."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from stockradar.jobs.cron_dispatch_watchdog import (
    TARGETS,
    WATCHDOG_CRON_TO_TARGET,
    WorkflowRun,
    evaluate,
    map_schedule_cron,
    parse_runs,
)

pytestmark = pytest.mark.unit


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def test_map_watchdog_crons() -> None:
    assert map_schedule_cron("20 7 * * *") == "daily"
    assert map_schedule_cron("35 3 * * *") == "patch"
    assert map_schedule_cron("15 2 1 * *") == "monthly"
    with pytest.raises(ValueError, match="unknown_watchdog_cron"):
        map_schedule_cron("45 6 * * *")


def test_aug26_2026_daily_miss_after_grace() -> None:
    verdict = evaluate(
        spec=TARGETS["daily"],
        now_utc=_dt("2026-08-26T07:20:00Z"),
        tokyo_date=date(2026, 8, 26),
        is_open=True,
        runs=[],
    )
    assert verdict.outcome == "miss"
    assert verdict.miss is True
    assert verdict.workflow_file == "daily.yml"


def test_aug26_2026_daily_ok_when_dispatch_exists() -> None:
    verdict = evaluate(
        spec=TARGETS["daily"],
        now_utc=_dt("2026-08-26T07:20:00Z"),
        tokyo_date=date(2026, 8, 26),
        is_open=True,
        runs=[
            WorkflowRun(
                created_at=_dt("2026-08-26T06:45:49Z"),
                event="workflow_dispatch",
                status="completed",
                html_url="https://example.test/daily",
            )
        ],
    )
    assert verdict.outcome == "ok"
    assert verdict.covering_run_url == "https://example.test/daily"


def test_previous_day_run_does_not_cover() -> None:
    verdict = evaluate(
        spec=TARGETS["daily"],
        now_utc=_dt("2026-08-26T07:20:00Z"),
        tokyo_date=date(2026, 8, 26),
        is_open=True,
        runs=[
            WorkflowRun(
                created_at=_dt("2026-08-25T06:45:49Z"),
                event="workflow_dispatch",
                status="completed",
                html_url="https://example.test/yesterday",
            )
        ],
    )
    assert verdict.outcome == "miss"


def test_closed_session_skips_daily() -> None:
    verdict = evaluate(
        spec=TARGETS["daily"],
        now_utc=_dt("2026-08-23T07:20:00Z"),
        tokyo_date=date(2026, 8, 23),
        is_open=False,
        runs=[],
    )
    assert verdict.outcome == "skip_closed"
    assert verdict.miss is False


def test_too_early_before_grace() -> None:
    verdict = evaluate(
        spec=TARGETS["daily"],
        now_utc=_dt("2026-08-26T06:50:00Z"),
        tokyo_date=date(2026, 8, 26),
        is_open=True,
        runs=[],
    )
    assert verdict.outcome == "too_early"


def test_patch_miss_independent_of_daily() -> None:
    verdict = evaluate(
        spec=TARGETS["patch"],
        now_utc=_dt("2026-08-26T03:35:00Z"),
        tokyo_date=date(2026, 8, 26),
        is_open=True,
        runs=[],
    )
    assert verdict.outcome == "miss"
    assert verdict.workflow_file == "daily_universe_patch.yml"


def test_monthly_does_not_require_trading_day() -> None:
    verdict = evaluate(
        spec=TARGETS["monthly"],
        now_utc=_dt("2026-08-01T02:15:00Z"),
        tokyo_date=date(2026, 8, 1),
        is_open=False,
        runs=[
            WorkflowRun(
                created_at=_dt("2026-08-01T02:00:12Z"),
                event="workflow_dispatch",
                status="in_progress",
                html_url="https://example.test/monthly",
            )
        ],
    )
    assert verdict.outcome == "ok"


def test_parse_github_runs_payload() -> None:
    runs = parse_runs(
        {
            "workflow_runs": [
                {
                    "created_at": "2026-08-26T06:45:49Z",
                    "event": "workflow_dispatch",
                    "status": "completed",
                    "html_url": "https://example.test/r",
                }
            ]
        }
    )
    assert len(runs) == 1
    assert runs[0].created_at == datetime(2026, 8, 26, 6, 45, 49, tzinfo=timezone.utc)


def test_watchdog_cron_table_covers_all_targets() -> None:
    assert set(WATCHDOG_CRON_TO_TARGET.values()) == set(TARGETS)
