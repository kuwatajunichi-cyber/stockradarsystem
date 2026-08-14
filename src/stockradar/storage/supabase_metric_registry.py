"""Supabase metric registry adapter (Phase 4.5 production)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from stockradar.storage.metric_registry import ActiveMetricSetCasConflictError, MetricRegistryPort
from stockradar.storage.supabase_client import (
    ENV_SUPABASE_SECRET_KEY,
    ENV_SUPABASE_URL,
    _auth_headers,
)


@dataclass
class SupabaseMetricRegistryAdapter:
    base_url: str
    secret_key: str
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> SupabaseMetricRegistryAdapter:
        url = os.environ.get(ENV_SUPABASE_URL, "").strip().rstrip("/")
        key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
        if not url or not key:
            raise RuntimeError(f"{ENV_SUPABASE_URL} and {ENV_SUPABASE_SECRET_KEY} are required")
        return cls(base_url=url, secret_key=key)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        headers = _auth_headers(self.secret_key)
        if prefer:
            headers["Prefer"] = prefer
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout_s) as client:
            return client.request(method, url, headers=headers, json=json_body, params=params)

    def get_active_metric_set_id(self) -> str | None:
        resp = self._request(
            "GET",
            "/rest/v1/active_metric_set",
            params={
                "pointer_key": "eq.default",
                "select": "metric_set_version_id",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        value = rows[0].get("metric_set_version_id")
        return str(value) if value else None

    def get_metric_set_version(self, set_id: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/metric_set_versions",
            params={
                "id": f"eq.{set_id.strip()}",
                "select": "id,lifecycle_status,set_key",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        return {
            "id": str(row.get("id")),
            "lifecycle_status": str(row.get("lifecycle_status") or "draft"),
            "set_key": row.get("set_key"),
        }

    def activate_metric_set_cas(
        self,
        *,
        expected_set_id: str | None,
        new_set_id: str,
        writer_workflow: str,
        source_github_run_id: int,
    ) -> None:
        body = {
            "p_expected_set_id": expected_set_id,
            "p_new_set_id": new_set_id,
            "p_writer_workflow": writer_workflow,
            "p_source_github_run_id": source_github_run_id,
        }
        resp = self._request("POST", "/rest/v1/rpc/activate_metric_set_cas", json_body=body)
        if resp.status_code >= 400:
            text = resp.text
            if "active_metric_set_cas_conflict" in text or "cas_conflict" in text.lower():
                raise ActiveMetricSetCasConflictError(text)
            resp.raise_for_status()
        resp.raise_for_status()
