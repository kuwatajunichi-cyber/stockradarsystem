from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.job_integration

_EXIT_FAILED_PATTERN = re.compile(
    r'if \[ "\$STATUS" = "failed" \][\s\S]*?exit 1',
    re.MULTILINE,
)
_DAILY_EXIT_FAILED_PATTERN = re.compile(
    r'if \[ "\$\{\{ steps\.terminal\.outputs\.status \}\}" = "failed" \][\s\S]*?exit 1',
    re.MULTILINE,
)


def _workflow_text(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / ".github" / "workflows" / name).read_text(
        encoding="utf-8"
    )


def _finalize_run_block(text: str) -> str:
    start = text.find("finalize_run:")
    assert start >= 0, "finalize_run job not found"
    return text[start:]


@pytest.mark.job_integration
def test_daily_finalize_propagates_terminal_failed_to_workflow() -> None:
    block = _finalize_run_block(_workflow_text("daily.yml"))
    assert _DAILY_EXIT_FAILED_PATTERN.search(block), "daily.yml must exit 1 when terminal status is failed"


@pytest.mark.job_integration
@pytest.mark.parametrize(
    "workflow",
    [
        "monthly.yml",
        "daily_universe_patch.yml",
        "daily_event_cause_enrichment.yml",
    ],
)
def test_single_step_finalize_propagates_status_failed(workflow: str) -> None:
    block = _finalize_run_block(_workflow_text(workflow))
    assert _EXIT_FAILED_PATTERN.search(block), f"{workflow} must exit 1 when STATUS=failed"
