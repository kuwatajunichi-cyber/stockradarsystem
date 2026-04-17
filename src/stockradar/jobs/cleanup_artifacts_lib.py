"""Pure helpers for GitHub Actions artifact cleanup (age + prefix rules)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class CleanupRule:
    prefix: str
    keep_days: int
    enabled: bool = True
    max_delete: int = 200


def coerce_yaml_bool(value: Any, *, field: str) -> bool:
    """Parse YAML/config booleans without Python ``bool("false") == True`` pitfalls."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
        raise ValueError(f"{field}: expected 0 or 1 for integer bool, got {value!r}")
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "1", "on"):
            return True
        if s in ("false", "no", "0", "off"):
            return False
        if s == "":
            raise ValueError(f"{field}: empty string is not a valid boolean")
        raise ValueError(f"{field}: invalid boolean string {value!r}")
    raise ValueError(f"{field}: expected bool, 0/1, or string, got {type(value).__name__}")


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
