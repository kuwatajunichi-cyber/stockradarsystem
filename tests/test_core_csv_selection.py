from datetime import date

import pytest

from stockradar.jobs.core_csv_selection import (
    count_unparseable_patched_prefixed_keys,
    parse_universe_patched_key,
    select_patched_cache_key,
)

pytestmark = pytest.mark.unit


def test_count_unparseable_patched_prefixed_keys() -> None:
    keys = [
        "universe-patched-bad-no-date-suffix",
        "universe-patched-trailing-junk-2026-04-10suffix",
        "other-key",
        "universe-patched-monthly-20260207-1-2026-04-10",
    ]
    assert count_unparseable_patched_prefixed_keys(keys) == 2


def test_parse_universe_patched_key() -> None:
    tag, d = parse_universe_patched_key("universe-patched-monthly-20260207-1-2026-04-10")
    assert tag == "monthly-20260207-1"
    assert d == date(2026, 4, 10)


def test_select_patched_cache_key_nearest() -> None:
    monthly = "monthly-20260207-1"
    run = date(2026, 4, 15)
    keys = [
        f"universe-patched-{monthly}-2026-04-01",
        f"universe-patched-{monthly}-2026-04-10",
        f"universe-patched-{monthly}-2026-04-20",
        "universe-patched-other-2026-04-10",
    ]
    assert select_patched_cache_key(keys, monthly_tag=monthly, run_date=run) == f"universe-patched-{monthly}-2026-04-10"


def test_select_patched_cache_key_none_other_month() -> None:
    monthly = "monthly-20260207-1"
    run = date(2026, 5, 1)
    keys = [f"universe-patched-{monthly}-2026-04-30"]
    assert select_patched_cache_key(keys, monthly_tag=monthly, run_date=run) is None