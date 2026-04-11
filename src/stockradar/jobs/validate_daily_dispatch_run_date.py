"""
Validate workflow_dispatch run_date; set is_replay for daily workflow.

Empty input: normal run. Same as Tokyo today: normal run. Else replay within 3 calendar months.
Appends is_replay to GITHUB_OUTPUT when set.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

import pytz

from stockradar.universe.monthly_release_pick import subtract_calendar_months


def _today_tokyo() -> date:
    tz = pytz.timezone("Asia/Tokyo")
    return datetime.now(tz).date()


def validate_input(raw: str) -> tuple[bool, date | None]:
    s = (raw or "").strip()
    if not s:
        return False, None
    d = date.fromisoformat(s)
    today = _today_tokyo()
    if d > today:
        raise ValueError(f"run_date must not be after Tokyo today ({today})")
    if d == today:
        return False, d
    min_d = subtract_calendar_months(today, 3)
    if d < min_d:
        raise ValueError(
            f"replay run_date must be within the last 3 calendar months "
            f"(min allowed={min_d}, got={d})"
        )
    return True, d


def _append_github_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate dispatch run_date for daily replay.")
    parser.add_argument("--input-run-date", type=str, default="")
    args = parser.parse_args(argv)
    raw = os.environ.get("INPUT_RUN_DATE", args.input_run_date or "")

    try:
        is_replay, _parsed = validate_input(raw)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    val = "true" if is_replay else "false"
    print(f"is_replay={val}")
    _append_github_output("is_replay", val)


if __name__ == "__main__":
    main()