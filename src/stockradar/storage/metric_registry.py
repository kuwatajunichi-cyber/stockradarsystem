"""Phase 4.5 metric registry Fake adapter + CAS contract (Secrets-free)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


class ActiveMetricSetCasConflictError(RuntimeError):
    """CAS mismatch — no mutation (exit 2 contract)."""


@dataclass
class FakeMetricRegistryStore:
    metric_set_versions: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_metric_set: dict[str, Any] | None = None

    def get_active_metric_set_id(self) -> str | None:
        if self.active_metric_set is None:
            return None
        return str(self.active_metric_set.get("metric_set_version_id") or "") or None

    def activate_metric_set_cas(
        self,
        *,
        expected_set_id: str | None,
        new_set_id: str,
        writer_workflow: str,
        source_github_run_id: int,
    ) -> None:
        current = self.get_active_metric_set_id()
        if current != expected_set_id:
            raise ActiveMetricSetCasConflictError(
                f"expected {expected_set_id!r}, current {current!r}"
            )
        if new_set_id not in self.metric_set_versions:
            raise RuntimeError(f"unknown metric_set_version: {new_set_id}")
        if current == new_set_id:
            self.active_metric_set = {
                "pointer_key": "default",
                "metric_set_version_id": new_set_id,
                "writer_workflow": writer_workflow,
                "source_github_run_id": source_github_run_id,
            }
            return
        new_row = self.metric_set_versions[new_set_id]
        if new_row.get("lifecycle_status") not in ("shadow", "retired"):
            raise RuntimeError(
                f"set {new_set_id!r} not activatable (requires shadow or retired)"
            )
        new_row = self.metric_set_versions[new_set_id]
        new_row["lifecycle_status"] = "active"
        for sid, row in self.metric_set_versions.items():
            if sid != new_set_id and row.get("lifecycle_status") == "active":
                row["lifecycle_status"] = "retired"
        self.active_metric_set = {
            "pointer_key": "default",
            "metric_set_version_id": new_set_id,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
        }

    def seed_set(self, *, set_id: str | None = None, lifecycle: str = "shadow") -> str:
        sid = set_id or str(uuid4())
        self.metric_set_versions[sid] = {
            "id": sid,
            "set_key": f"ms-{sid[:8]}",
            "lifecycle_status": lifecycle,
        }
        return sid
