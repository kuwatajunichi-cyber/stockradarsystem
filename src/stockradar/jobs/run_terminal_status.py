"""Pure daily run terminal status resolution (Phase 4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

JobResult = Literal["success", "failure", "skipped", "cancelled"]


@dataclass(frozen=True)
class DailyRunTerminalInput:
    is_open: bool
    compute_indicators: JobResult
    event_cause_enrichment: JobResult
    render_and_upload: JobResult
    skip_publish: bool
    upload_executed: bool
    upload_exit_code: int
    upload_status: str = "ok"


@dataclass(frozen=True)
class DailyRunTerminalDecision:
    status: Literal["success", "failed"]
    degraded_reason: str | None = None


def _strict_job_failed(result: JobResult) -> bool:
    return result != "success"


def _optional_job_failed(result: JobResult) -> bool:
    return result in {"failure", "cancelled"}


def resolve_daily_run_terminal_status(inp: DailyRunTerminalInput) -> DailyRunTerminalDecision:
    if not inp.is_open:
        return DailyRunTerminalDecision(status="success", degraded_reason="market_closed")

    if _strict_job_failed(inp.compute_indicators):
        return DailyRunTerminalDecision(status="failed")
    if _optional_job_failed(inp.event_cause_enrichment):
        return DailyRunTerminalDecision(status="failed")
    if _strict_job_failed(inp.render_and_upload):
        return DailyRunTerminalDecision(status="failed")

    if not inp.skip_publish and (
        not inp.upload_executed
        or inp.upload_exit_code != 0
        or inp.upload_status == "degraded"
    ):
        return DailyRunTerminalDecision(status="failed")

    return DailyRunTerminalDecision(status="success")
