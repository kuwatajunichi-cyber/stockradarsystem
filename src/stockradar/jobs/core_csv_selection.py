"""
Pure logic: pick patched universe cache key from listed keys.

Contract: key format ``universe-patched-{MONTHLY_TAG}-{YYYY-MM-DD}`` (date suffix at end).

配置: I/O を持たないため ``stockradar.utils`` に置けるが、日次の
``resolve_core_csv`` からのみ参照される補助ロジックとして ``jobs`` 配下に置いている。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Final

PATCHED_KEY_PREFIX: Final[str] = "universe-patched-"
_SUFFIX_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")


def parse_universe_patched_key(key: str) -> tuple[str, date] | None:
    if not key.startswith(PATCHED_KEY_PREFIX):
        return None
    rest = key[len(PATCHED_KEY_PREFIX) :]
    m = _SUFFIX_DATE_RE.search(rest)
    if not m:
        return None
    suffix = m.group(1)
    try:
        patch_run_d = date.fromisoformat(suffix)
    except ValueError:
        return None
    monthly_tag = rest[: m.start(1)].rstrip("-")
    if not monthly_tag:
        return None
    return monthly_tag, patch_run_d


def count_unparseable_patched_prefixed_keys(cache_keys: list[str]) -> int:
    """Count keys that look like patched-universe caches but fail strict parse."""
    n = 0
    for key in cache_keys:
        if not key.startswith(PATCHED_KEY_PREFIX):
            continue
        if parse_universe_patched_key(key) is None:
            n += 1
    return n


def select_patched_cache_key(
    cache_keys: list[str],
    *,
    monthly_tag: str,
    run_date: date,
) -> str | None:
    """Same MONTHLY_TAG, same calendar month as run_date, patch date <= run_date; pick latest."""
    candidates: list[tuple[date, str]] = []
    for key in cache_keys:
        parsed = parse_universe_patched_key(key)
        if parsed is None:
            continue
        tag, patch_d = parsed
        if tag != monthly_tag:
            continue
        if patch_d.year != run_date.year or patch_d.month != run_date.month:
            continue
        if patch_d > run_date:
            continue
        candidates.append((patch_d, key))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[-1][1]
