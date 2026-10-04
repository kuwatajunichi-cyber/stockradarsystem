"""Backfill CLI must not report ok for a short as-of list."""
from __future__ import annotations

import pytest

from scripts.storage.web_asof_backfill_cli import backfill_coverage_status

pytestmark = pytest.mark.unit


def test_backfill_coverage_not_met_when_found_short_of_requested() -> None:
    status, code = backfill_coverage_status(requested=60, found=59, remaining=[])
    assert status == "not_met"
    assert code == 1


def test_backfill_coverage_ok_when_requested_met() -> None:
    status, code = backfill_coverage_status(requested=60, found=60, remaining=[])
    assert status == "ok"
    assert code == 0


def test_backfill_coverage_error_when_remaining() -> None:
    status, code = backfill_coverage_status(
        requested=60, found=60, remaining=["2026-07-08"]
    )
    assert status == "error"
    assert code == 1
