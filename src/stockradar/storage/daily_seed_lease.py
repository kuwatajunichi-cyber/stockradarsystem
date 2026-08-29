"""Daily membership trim when seed holds an active series lease (ADR-005)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence


@dataclass(frozen=True)
class LeaseSkipDecision:
    remaining_codes: tuple[str, ...]
    skipped_codes: tuple[str, ...]
    flags: tuple[str, ...]
    waited_seconds: float = 0.0


def filter_membership_after_seed_lease_wait(
    *,
    membership_codes: Sequence[str],
    active_seed_lease_codes: Iterable[str],
    waited_seconds: float,
    max_wait_seconds: float = 120.0,
) -> LeaseSkipDecision:
    """After waiting, drop codes that still hold an active seed lease.

    Call this BEFORE begin_derived_generation so expected_object_count matches
    the trimmed membership. Exit code stays 0; flag daily_seed_lease_skip.
    """
    blocked = {str(c).strip() for c in active_seed_lease_codes if str(c).strip()}
    remaining: list[str] = []
    skipped: list[str] = []
    for code in membership_codes:
        c = str(code).strip()
        if not c:
            continue
        if c in blocked and waited_seconds >= max_wait_seconds:
            skipped.append(c)
        else:
            remaining.append(c)
    flags = ("daily_seed_lease_skip",) if skipped else ()
    return LeaseSkipDecision(
        remaining_codes=tuple(remaining),
        skipped_codes=tuple(skipped),
        flags=flags,
        waited_seconds=float(waited_seconds),
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lease_deadline(*, started_at: datetime, max_wait_seconds: float = 120.0) -> datetime:
    return started_at + timedelta(seconds=float(max_wait_seconds))


def list_active_seed_lease_codes_from_rows(
    rows: Iterable[dict],
    *,
    membership_codes: Sequence[str],
    now: datetime | None = None,
) -> list[str]:
    """Return membership codes that still have unexpired series_seed/repair leases."""
    now_dt = now or utc_now()
    wanted = {str(c).strip() for c in membership_codes if str(c).strip()}
    active: list[str] = []
    for row in rows:
        code = str(row.get("instrument_code") or "").strip()
        if code not in wanted:
            continue
        owner = str(row.get("owner_kind") or "")
        if owner not in {"series_seed", "series_repair"}:
            continue
        expires = row.get("expires_at")
        if expires is None:
            continue
        if isinstance(expires, str):
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        elif isinstance(expires, datetime):
            exp = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
        else:
            continue
        if exp > now_dt:
            active.append(code)
    return sorted(set(active))


def wait_and_collect_seed_lease_skips(
    *,
    membership_codes: Sequence[str],
    fetch_active_rows,
    max_wait_seconds: float = 120.0,
    poll_seconds: float = 5.0,
    sleep_fn=None,
    now_fn=None,
) -> LeaseSkipDecision:
    """Poll leases up to max_wait, then apply filter_membership_after_seed_lease_wait."""
    import time as _time

    sleep = sleep_fn or _time.sleep
    started = (now_fn or utc_now)()
    waited = 0.0
    while waited < float(max_wait_seconds):
        rows = list(fetch_active_rows())
        active = list_active_seed_lease_codes_from_rows(
            rows, membership_codes=membership_codes, now=(now_fn or utc_now)()
        )
        if not active:
            return filter_membership_after_seed_lease_wait(
                membership_codes=membership_codes,
                active_seed_lease_codes=[],
                waited_seconds=waited,
                max_wait_seconds=max_wait_seconds,
            )
        sleep(min(float(poll_seconds), float(max_wait_seconds) - waited))
        waited = ((now_fn or utc_now)() - started).total_seconds()
    rows = list(fetch_active_rows())
    active = list_active_seed_lease_codes_from_rows(
        rows, membership_codes=membership_codes, now=(now_fn or utc_now)()
    )
    return filter_membership_after_seed_lease_wait(
        membership_codes=membership_codes,
        active_seed_lease_codes=active,
        waited_seconds=max(waited, float(max_wait_seconds)),
        max_wait_seconds=max_wait_seconds,
    )
