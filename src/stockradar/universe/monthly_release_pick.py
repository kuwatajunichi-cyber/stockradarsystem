"""
Pick monthly-* GitHub Release tag for run_date (pure).
Contract: docs/contracts/daily_replay_and_monthly_universe.md
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

MONTHLY_TAG_RE = re.compile(r"^monthly-(\d{8})-(\d+)$")
UniverseResolution = Literal["time_series_ok", "fallback_latest"]


@dataclass(frozen=True)
class MonthlyReleasePick:
    tag: str
    universe_resolution: UniverseResolution
    reason: str


def parse_monthly_tag(tag: str) -> tuple[date, int] | None:
    m = MONTHLY_TAG_RE.match(tag.strip())
    if not m:
        return None
    ymd, rid_s = m.group(1), m.group(2)
    y, mo, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])
    try:
        snap = date(y, mo, d)
    except ValueError:
        return None
    return snap, int(rid_s)


def pick_monthly_release(run_date: date, tags: Sequence[str]) -> MonthlyReleasePick:
    if not tags:
        raise ValueError("monthly release tags list is empty")

    ordered_valid: list[str] = []
    eligible: list[tuple[str, date, int]] = []
    for raw in tags:
        t = raw.strip()
        if not t:
            continue
        parsed = parse_monthly_tag(t)
        if parsed is None:
            continue
        snap, rid = parsed
        ordered_valid.append(t)
        if snap <= run_date:
            eligible.append((t, snap, rid))

    if not ordered_valid:
        raise ValueError("no parsable monthly-YYYYMMDD-<run_id> tags in list")

    if eligible:
        best_tag, _, _ = max(eligible, key=lambda x: (x[1], x[2]))
        return MonthlyReleasePick(tag=best_tag, universe_resolution="time_series_ok", reason="")

    fb = ordered_valid[0]
    return MonthlyReleasePick(
        tag=fb,
        universe_resolution="fallback_latest",
        reason=(
            f"no monthly tag with snapshot_date<={run_date.isoformat()}; "
            f"using first parsable tag in list order ({fb})"
        ),
    )


def subtract_calendar_months(d: date, months: int) -> date:
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    day = min(d.day, last)
    return date(y, m, day)