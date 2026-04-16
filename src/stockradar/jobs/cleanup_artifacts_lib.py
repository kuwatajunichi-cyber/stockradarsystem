"""Pure helpers for GitHub Actions artifact cleanup (age + prefix rules)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class CleanupRule:
    prefix: str
    keep_days: int
    enabled: bool = True
    max_delete: int = 200


def parse_github_datetime(created_at: str) -> float:
    """Parse GitHub API ``created_at`` (RFC3339) to epoch seconds (UTC)."""
    s = created_at.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def cutoff_epoch_utc(*, keep_days: int, now: datetime | None = None) -> float:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base - timedelta(days=keep_days)).timestamp()


def should_delete_artifact(
    name: str,
    created_at: str,
    *,
    prefix: str,
    cutoff_epoch: float,
) -> bool:
    if not name.startswith(prefix):
        return False
    try:
        return parse_github_datetime(created_at) < cutoff_epoch
    except ValueError:
        return False
