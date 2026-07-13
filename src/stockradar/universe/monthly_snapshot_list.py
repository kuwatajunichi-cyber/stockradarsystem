"""List committed monthly snapshot tags from Supabase (Phase 4)."""
from __future__ import annotations

from typing import Protocol


class MonthlySnapshotListPort(Protocol):
    def list_committed_monthly_tags(self) -> list[str]: ...


def list_committed_monthly_tags(adapter: MonthlySnapshotListPort) -> list[str]:
    return adapter.list_committed_monthly_tags()
