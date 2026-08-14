from __future__ import annotations

import pytest

from stockradar.jobs.run_terminal_status import DailyRunTerminalInput, resolve_daily_run_terminal_status


@pytest.mark.unit
def test_market_closed_success() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=False,
            compute_indicators="skipped",
            event_cause_enrichment="skipped",
            render_and_upload="skipped",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
        )
    )
    assert d.status == "success" and d.degraded_reason == "market_closed"


@pytest.mark.unit
def test_required_job_skipped_is_failed() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="skipped",
            event_cause_enrichment="success",
            render_and_upload="success",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
        )
    )
    assert d.status == "failed"


@pytest.mark.unit
def test_publish_required_without_upload_is_failed() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="success",
            render_and_upload="success",
            skip_publish=False,
            upload_executed=False,
            upload_exit_code=0,
        )
    )
    assert d.status == "failed"

@pytest.mark.unit
def test_optional_enrichment_skipped_does_not_fail_open_day_run() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="skipped",
            render_and_upload="success",
            skip_publish=False,
            upload_executed=True,
            upload_exit_code=0,
        )
    )
    assert d.status == "success"

@pytest.mark.unit
def test_upload_degraded_is_failed_when_publish_required() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="success",
            render_and_upload="success",
            skip_publish=False,
            upload_executed=True,
            upload_exit_code=0,
            upload_status="degraded",
        )
    )
    assert d.status == "failed"


@pytest.mark.unit
def test_enrichment_failure_is_failed_on_open_day() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="failure",
            render_and_upload="success",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
        )
    )
    assert d.status == "failed"


@pytest.mark.unit
def test_enrichment_cancelled_is_failed_on_open_day() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="cancelled",
            render_and_upload="success",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
        )
    )
    assert d.status == "failed"


@pytest.mark.unit
def test_write_derived_failure_is_failed_on_open_day() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="success",
            render_and_upload="success",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
            write_derived_generation="failure",
        )
    )
    assert d.status == "failed"


@pytest.mark.unit
def test_write_derived_skipped_does_not_fail_open_day_run() -> None:
    d = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=True,
            compute_indicators="success",
            event_cause_enrichment="success",
            render_and_upload="success",
            skip_publish=True,
            upload_executed=False,
            upload_exit_code=0,
            write_derived_generation="skipped",
        )
    )
    assert d.status == "success"
