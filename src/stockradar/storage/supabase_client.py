"""Supabase control plane REST client (PostgREST + RPC)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

import httpx

ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_SUPABASE_SECRET_KEY = "SUPABASE_SECRET_KEY"


class SupabaseControlPort(Protocol):
    def upsert_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        run_date: str | None,
        status: str = "running",
    ) -> dict[str, Any]: ...

    def get_run(self, *, workflow: str, github_run_id: int) -> dict[str, Any] | None: ...

    def insert_artifact_index_pending(
        self,
        *,
        run_id: str,
        source_name: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        content_type: str,
        retention_policy: str | None = None,
    ) -> dict[str, Any]: ...

    def commit_artifact_index(self, *, artifact_id: str) -> dict[str, Any]: ...

    def mark_artifact_index_orphan(self, *, artifact_id: str) -> None: ...

    def insert_cache_index_pending_fixed(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
    ) -> dict[str, Any]: ...

    def commit_fixed_cache_rpc(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str: ...

    def mark_cache_index_orphan(self, *, cache_index_id: str) -> None: ...

    def upsert_cache_index_pending_patched(
        self,
        *,
        cache_key: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        source_ref: str,
    ) -> dict[str, Any]: ...

    def commit_cache_index_patched(
        self,
        *,
        cache_index_id: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
    ) -> dict[str, Any]: ...

    def list_patched_cache_rows(self) -> list[dict[str, Any]]: ...

    def get_patched_cache_row(self, *, cache_key: str) -> dict[str, Any] | None: ...

    def get_cache_index_patched(self, *, cache_key: str) -> dict[str, Any] | None: ...

    def get_cache_pointer(self, *, cache_key: str) -> dict[str, Any] | None: ...


    def _orphan_rows_optional(self, table: str) -> list[dict[str, Any]]:
        try:
            resp = self._request(
                "GET",
                f"/rest/v1/{table}",
                params={"status": "eq.orphan", "select": "*"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Phase 4 tables may be absent until migration U-1 is applied.
            if exc.response.status_code in {400, 404}:
                return []
            raise
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        return rows

    def list_orphan_rows(self) -> list[dict[str, Any]]: ...

    def delete_row(self, *, table: str, row_id: str) -> None: ...

    def update_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        status: str,
        degraded_reason: str | None = None,
        include_degraded_reason: bool = False,
    ) -> dict[str, Any]: ...

    def insert_monthly_snapshot_pending(
        self,
        *,
        monthly_tag: str,
        snapshot_date: str,
        github_run_id: int,
        object_keys: dict[str, Any],
        sha256: str,
        writer_workflow: str = "monthly.yml",
    ) -> dict[str, Any]: ...

    def commit_monthly_snapshot(self, *, snapshot_id: str) -> dict[str, Any]: ...

    def mark_monthly_snapshot_orphan(self, *, snapshot_id: str) -> None: ...

    def list_committed_monthly_tags(self) -> list[str]: ...

    def insert_publish_status_pending(
        self,
        *,
        run_id: str,
        workflow: str,
        github_run_id: int,
        run_date: str,
        logical_kind: str,
        visibility: str,
        object_key: str,
        manifest_object_key: str,
        size_bytes: int,
        sha256: str,
        content_type: str,
    ) -> dict[str, Any]: ...

    def commit_publish_status(self, *, publish_id: str) -> dict[str, Any]: ...

    def mark_publish_status_orphan(self, *, publish_id: str) -> None: ...

    def get_publish_status(self, *, publish_id: str) -> dict[str, Any] | None: ...

    def commit_jpx_url_cache_rpc(
        self,
        *,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str: ...


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


@dataclass
class SupabaseRestAdapter:
    base_url: str
    secret_key: str
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> SupabaseRestAdapter:
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

    def upsert_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        run_date: str | None,
        status: str = "running",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "workflow": workflow,
            "github_run_id": github_run_id,
            "status": status,
        }
        if run_date:
            body["run_date"] = run_date
        resp = self._request(
            "POST",
            "/rest/v1/runs",
            json_body=body,
            params={"on_conflict": "workflow,github_run_id"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("upsert_run returned no row")
        return rows[0]

    def update_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        status: str,
        degraded_reason: str | None = None,
        include_degraded_reason: bool = False,
    ) -> dict[str, Any]:
        from datetime import datetime, timezone

        body: dict[str, Any] = {
            "status": status,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        if include_degraded_reason:
            body["degraded_reason"] = degraded_reason
        resp = self._request(
            "PATCH",
            "/rest/v1/runs",
            params={
                "workflow": f"eq.{workflow}",
                "github_run_id": f"eq.{github_run_id}",
            },
            json_body=body,
            prefer="return=representation",
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("update_run returned no row")
        return rows[0]

    def get_run(self, *, workflow: str, github_run_id: int) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/runs",
            params={
                "workflow": f"eq.{workflow}",
                "github_run_id": f"eq.{github_run_id}",
                "select": "*",
                "limit": "1",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        return rows[0]

    def insert_artifact_index_pending(
        self,
        *,
        run_id: str,
        source_name: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        content_type: str,
        retention_policy: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": run_id,
            "source_name": source_name,
            "object_key": object_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "content_type": content_type,
            "status": "pending",
        }
        if retention_policy:
            body["retention_policy"] = retention_policy
        resp = self._request(
            "POST",
            "/rest/v1/artifact_index",
            json_body=body,
            prefer="return=representation",
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0]

    def commit_artifact_index(self, *, artifact_id: str) -> dict[str, Any]:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        resp = self._request(
            "PATCH",
            "/rest/v1/artifact_index",
            params={"id": f"eq.{artifact_id}"},
            json_body={"status": "committed", "committed_at_utc": ts},
            prefer="return=representation",
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0]

    def mark_artifact_index_orphan(self, *, artifact_id: str) -> None:
        resp = self._request(
            "PATCH",
            "/rest/v1/artifact_index",
            params={"id": f"eq.{artifact_id}"},
            json_body={"status": "orphan"},
        )
        resp.raise_for_status()

    def insert_cache_index_pending_fixed(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
    ) -> dict[str, Any]:
        body = {
            "cache_key": cache_key,
            "cache_kind": "fixed",
            "object_key": object_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
            "source_ref": "n/a",
            "status": "pending",
        }
        existing_resp = self._request(
            "GET",
            "/rest/v1/cache_index",
            params={
                "cache_key": f"eq.{cache_key}",
                "sha256": f"eq.{sha256}",
                "cache_kind": "eq.fixed",
                "status": "in.(pending,orphan)",
                "select": "id",
                "limit": "1",
            },
        )
        existing_resp.raise_for_status()
        rows = existing_resp.json()
        if isinstance(rows, list) and rows:
            row_id = str(rows[0]["id"])
            resp = self._request(
                "PATCH",
                "/rest/v1/cache_index",
                params={"id": f"eq.{row_id}"},
                json_body=body,
                prefer="return=representation",
            )
        else:
            resp = self._request(
                "POST",
                "/rest/v1/cache_index",
                json_body=body,
                prefer="return=representation",
            )
        resp.raise_for_status()
        return resp.json()[0]

    def commit_fixed_cache_rpc(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str:
        body: dict[str, Any] = {
            "p_cache_key": cache_key,
            "p_object_key": object_key,
            "p_sha256": sha256,
            "p_size_bytes": size_bytes,
            "p_writer_workflow": writer_workflow,
            "p_source_github_run_id": source_github_run_id,
        }
        if history_id:
            body["p_history_id"] = history_id
        resp = self._request("POST", "/rest/v1/rpc/commit_fixed_cache", json_body=body)
        resp.raise_for_status()
        result = resp.json()
        return str(result)

    def mark_cache_index_orphan(self, *, cache_index_id: str) -> None:
        resp = self._request(
            "PATCH",
            "/rest/v1/cache_index",
            params={"id": f"eq.{cache_index_id}"},
            json_body={"status": "orphan"},
        )
        resp.raise_for_status()

    def upsert_cache_index_pending_patched(
        self,
        *,
        cache_key: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        source_ref: str,
    ) -> dict[str, Any]:
        body = {
            "cache_key": cache_key,
            "cache_kind": "patched",
            "object_keys": object_keys,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
            "source_ref": source_ref,
            "status": "pending",
        }
        existing = self.get_cache_index_patched(cache_key=cache_key)
        if existing is not None:
            resp = self._request(
                "PATCH",
                "/rest/v1/cache_index",
                params={"id": f"eq.{existing['id']}"},
                json_body=body,
                prefer="return=representation",
            )
        else:
            resp = self._request(
                "POST",
                "/rest/v1/cache_index",
                json_body=body,
                prefer="return=representation",
            )
        resp.raise_for_status()
        return resp.json()[0]

    def commit_cache_index_patched(
        self,
        *,
        cache_index_id: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
    ) -> dict[str, Any]:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        resp = self._request(
            "PATCH",
            "/rest/v1/cache_index",
            params={"id": f"eq.{cache_index_id}"},
            json_body={
                "status": "committed",
                "object_keys": object_keys,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "committed_at_utc": ts,
            },
            prefer="return=representation",
        )
        resp.raise_for_status()
        return resp.json()[0]

    def list_patched_cache_rows(self) -> list[dict[str, Any]]:
        resp = self._request(
            "GET",
            "/rest/v1/cache_index",
            params={
                "cache_kind": "eq.patched",
                "status": "eq.committed",
                "select": "cache_key,source_ref",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows if isinstance(rows, list) else []

    def get_patched_cache_row(self, *, cache_key: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/cache_index",
            params={
                "cache_key": f"eq.{cache_key}",
                "cache_kind": "eq.patched",
                "status": "eq.committed",
                "select": "*",
                "limit": "1",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        return rows[0]

    def get_cache_index_patched(self, *, cache_key: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/cache_index",
            params={
                "cache_key": f"eq.{cache_key}",
                "cache_kind": "eq.patched",
                "select": "*",
                "limit": "1",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        return rows[0]

    def get_cache_pointer(self, *, cache_key: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/cache_pointers",
            params={"cache_key": f"eq.{cache_key}", "select": "*", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        return rows[0]


    def _orphan_rows_optional(self, table: str) -> list[dict[str, Any]]:
        try:
            resp = self._request(
                "GET",
                f"/rest/v1/{table}",
                params={"status": "eq.orphan", "select": "*"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Phase 4 tables may be absent until migration U-1 is applied.
            if exc.response.status_code in {400, 404}:
                return []
            raise
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        return rows

    def list_orphan_rows(self) -> list[dict[str, Any]]:
        artifacts = self._request(
            "GET",
            "/rest/v1/artifact_index",
            params={"status": "eq.orphan", "select": "*"},
        )
        artifacts.raise_for_status()
        caches = self._request(
            "GET",
            "/rest/v1/cache_index",
            params={"status": "eq.orphan", "select": "*"},
        )
        caches.raise_for_status()
        out: list[dict[str, Any]] = []
        for row in artifacts.json():
            row["_table"] = "artifact_index"
            out.append(row)
        for row in caches.json():
            row["_table"] = "cache_index"
            out.append(row)
        for row in self._orphan_rows_optional("monthly_snapshots"):
            row["_table"] = "monthly_snapshots"
            out.append(row)
        for row in self._orphan_rows_optional("publish_status"):
            row["_table"] = "publish_status"
            out.append(row)
        return out

    def insert_monthly_snapshot_pending(
        self,
        *,
        monthly_tag: str,
        snapshot_date: str,
        github_run_id: int,
        object_keys: dict[str, Any],
        sha256: str,
        writer_workflow: str = "monthly.yml",
    ) -> dict[str, Any]:
        body = {
            "monthly_tag": monthly_tag,
            "snapshot_date": snapshot_date,
            "github_run_id": github_run_id,
            "writer_workflow": writer_workflow,
            "object_keys": object_keys,
            "sha256": sha256,
            "status": "pending",
        }
        existing_resp = self._request(
            "GET",
            "/rest/v1/monthly_snapshots",
            params={
                "monthly_tag": f"eq.{monthly_tag}",
                "select": "id,status",
                "limit": "1",
            },
        )
        existing_resp.raise_for_status()
        rows = existing_resp.json()
        if isinstance(rows, list) and rows:
            row = rows[0]
            status = str(row.get("status") or "")
            row_id = str(row["id"])
            if status == "committed":
                full = self._request(
                    "GET",
                    "/rest/v1/monthly_snapshots",
                    params={"id": f"eq.{row_id}", "select": "*"},
                )
                full.raise_for_status()
                return full.json()[0]
            resp = self._request(
                "PATCH",
                "/rest/v1/monthly_snapshots",
                params={"id": f"eq.{row_id}"},
                json_body=body,
                prefer="return=representation",
            )
            resp.raise_for_status()
            return resp.json()[0]
        resp = self._request(
            "POST",
            "/rest/v1/monthly_snapshots",
            json_body=body,
            prefer="return=representation",
        )
        resp.raise_for_status()
        return resp.json()[0]

    def commit_monthly_snapshot(self, *, snapshot_id: str) -> dict[str, Any]:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        resp = self._request(
            "PATCH",
            "/rest/v1/monthly_snapshots",
            params={"id": f"eq.{snapshot_id}"},
            json_body={"status": "committed", "committed_at_utc": ts},
            prefer="return=representation",
        )
        resp.raise_for_status()
        return resp.json()[0]

    def mark_monthly_snapshot_orphan(self, *, snapshot_id: str) -> None:
        resp = self._request(
            "PATCH",
            "/rest/v1/monthly_snapshots",
            params={"id": f"eq.{snapshot_id}"},
            json_body={"status": "orphan"},
        )
        resp.raise_for_status()

    def list_committed_monthly_tags(self) -> list[str]:
        resp = self._request(
            "GET",
            "/rest/v1/monthly_snapshots",
            params={
                "status": "eq.committed",
                "select": "monthly_tag,snapshot_date,github_run_id",
                "order": "snapshot_date.desc,github_run_id.desc",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        return [str(r["monthly_tag"]) for r in rows if r.get("monthly_tag")]

    def insert_publish_status_pending(
        self,
        *,
        run_id: str,
        workflow: str,
        github_run_id: int,
        run_date: str,
        logical_kind: str,
        visibility: str,
        object_key: str,
        manifest_object_key: str,
        size_bytes: int,
        sha256: str,
        content_type: str,
    ) -> dict[str, Any]:
        body = {
            "run_id": run_id,
            "workflow": workflow,
            "github_run_id": github_run_id,
            "run_date": run_date,
            "logical_kind": logical_kind,
            "visibility": visibility,
            "object_key": object_key,
            "manifest_object_key": manifest_object_key,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "content_type": content_type,
            "status": "pending",
        }
        existing_resp = self._request(
            "GET",
            "/rest/v1/publish_status",
            params={
                "run_id": f"eq.{run_id}",
                "logical_kind": f"eq.{logical_kind}",
                "select": "id,status",
                "limit": "1",
            },
        )
        existing_resp.raise_for_status()
        rows = existing_resp.json()
        if isinstance(rows, list) and rows:
            row = rows[0]
            status = str(row.get("status") or "")
            row_id = str(row["id"])
            if status == "committed":
                full = self._request(
                    "GET",
                    "/rest/v1/publish_status",
                    params={"id": f"eq.{row_id}", "select": "*"},
                )
                full.raise_for_status()
                return full.json()[0]
            resp = self._request(
                "PATCH",
                "/rest/v1/publish_status",
                params={"id": f"eq.{row_id}"},
                json_body=body,
                prefer="return=representation",
            )
            resp.raise_for_status()
            return resp.json()[0]
        resp = self._request(
            "POST",
            "/rest/v1/publish_status",
            json_body=body,
            prefer="return=representation",
        )
        resp.raise_for_status()
        return resp.json()[0]

    def commit_publish_status(self, *, publish_id: str) -> dict[str, Any]:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        resp = self._request(
            "PATCH",
            "/rest/v1/publish_status",
            params={"id": f"eq.{publish_id}"},
            json_body={"status": "committed", "committed_at_utc": ts},
            prefer="return=representation",
        )
        resp.raise_for_status()
        return resp.json()[0]

    def mark_publish_status_orphan(self, *, publish_id: str) -> None:
        resp = self._request(
            "PATCH",
            "/rest/v1/publish_status",
            params={"id": f"eq.{publish_id}"},
            json_body={"status": "orphan"},
        )
        resp.raise_for_status()

    def get_publish_status(self, *, publish_id: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/rest/v1/publish_status",
            params={"id": f"eq.{publish_id}", "select": "*", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return rows[0]

    def commit_jpx_url_cache_rpc(
        self,
        *,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str:
        body: dict[str, Any] = {
            "p_object_key": object_key,
            "p_sha256": sha256,
            "p_size_bytes": size_bytes,
            "p_writer_workflow": writer_workflow,
            "p_source_github_run_id": source_github_run_id,
        }
        if history_id:
            body["p_history_id"] = history_id
        resp = self._request("POST", "/rest/v1/rpc/commit_jpx_url_cache", json_body=body)
        resp.raise_for_status()
        return str(resp.json())

    def delete_row(self, *, table: str, row_id: str) -> None:
        resp = self._request("DELETE", f"/rest/v1/{table}", params={"id": f"eq.{row_id}"})
        resp.raise_for_status()


@dataclass
class FakeSupabaseControlAdapter:
    """In-memory Supabase control plane for secrets-free tests."""

    runs: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    artifact_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    cache_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    cache_pointers: dict[str, dict[str, Any]] = field(default_factory=dict)
    monthly_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    publish_status: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        run_date: str | None,
        status: str = "running",
    ) -> dict[str, Any]:
        key = (workflow, github_run_id)
        row = self.runs.get(key)
        if row is None:
            row = {
                "id": str(uuid4()),
                "workflow": workflow,
                "github_run_id": github_run_id,
                "run_date": run_date,
                "status": status,
            }
            self.runs[key] = row
        else:
            row["status"] = status
            if run_date:
                row["run_date"] = run_date
        return dict(row)

    def update_run(
        self,
        *,
        workflow: str,
        github_run_id: int,
        status: str,
        degraded_reason: str | None = None,
        include_degraded_reason: bool = False,
    ) -> dict[str, Any]:
        key = (workflow, github_run_id)
        row = self.runs.get(key)
        if row is None:
            raise RuntimeError(f"runs row missing for {workflow} {github_run_id}")
        row["status"] = status
        row["finished_at_utc"] = "fake-ts"
        if include_degraded_reason:
            row["degraded_reason"] = degraded_reason
        return dict(row)

    def get_run(self, *, workflow: str, github_run_id: int) -> dict[str, Any] | None:
        row = self.runs.get((workflow, github_run_id))
        return dict(row) if row else None

    def insert_artifact_index_pending(
        self,
        *,
        run_id: str,
        source_name: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        content_type: str,
        retention_policy: str | None = None,
    ) -> dict[str, Any]:
        for row in self.artifact_index.values():
            if row["run_id"] == run_id and row["source_name"] == source_name:
                row.update(
                    {
                        "object_key": object_key,
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                        "content_type": content_type,
                        "status": "pending",
                    }
                )
                return dict(row)
        aid = str(uuid4())
        row = {
            "id": aid,
            "run_id": run_id,
            "source_name": source_name,
            "object_key": object_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "content_type": content_type,
            "status": "pending",
            "retention_policy": retention_policy,
        }
        self.artifact_index[aid] = row
        return dict(row)

    def commit_artifact_index(self, *, artifact_id: str) -> dict[str, Any]:
        row = self.artifact_index[artifact_id]
        row["status"] = "committed"
        row["committed_at_utc"] = "fake-ts"
        return dict(row)

    def mark_artifact_index_orphan(self, *, artifact_id: str) -> None:
        self.artifact_index[artifact_id]["status"] = "orphan"

    def insert_cache_index_pending_fixed(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
    ) -> dict[str, Any]:
        for existing in self.cache_index.values():
            if (
                existing.get("cache_key") == cache_key
                and existing.get("sha256") == sha256
                and existing.get("cache_kind") == "fixed"
                and existing.get("status") in {"pending", "orphan"}
            ):
                existing.update(
                    {
                        "object_key": object_key,
                        "size_bytes": size_bytes,
                        "writer_workflow": writer_workflow,
                        "source_github_run_id": source_github_run_id,
                        "source_ref": "n/a",
                        "status": "pending",
                    }
                )
                return dict(existing)
        cid = str(uuid4())
        row = {
            "id": cid,
            "cache_key": cache_key,
            "cache_kind": "fixed",
            "object_key": object_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
            "source_ref": "n/a",
            "status": "pending",
        }
        self.cache_index[cid] = row
        return dict(row)

    def commit_fixed_cache_rpc(
        self,
        *,
        cache_key: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str:
        if history_id and history_id in self.cache_index:
            self.cache_index[history_id]["status"] = "committed"
            hid = history_id
        else:
            hid = str(uuid4())
            self.cache_index[hid] = {
                "id": hid,
                "cache_key": cache_key,
                "cache_kind": "fixed",
                "object_key": object_key,
                "sha256": sha256,
                "status": "committed",
            }
        self.cache_pointers[cache_key] = {
            "cache_key": cache_key,
            "object_key": object_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
        }
        return hid

    def mark_cache_index_orphan(self, *, cache_index_id: str) -> None:
        self.cache_index[cache_index_id]["status"] = "orphan"

    def upsert_cache_index_pending_patched(
        self,
        *,
        cache_key: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        source_ref: str,
    ) -> dict[str, Any]:
        for row in self.cache_index.values():
            if row.get("cache_key") == cache_key and row.get("cache_kind") == "patched":
                row.update(
                    {
                        "object_keys": object_keys,
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                        "source_ref": source_ref,
                        "status": "pending",
                    }
                )
                return dict(row)
        cid = str(uuid4())
        row = {
            "id": cid,
            "cache_key": cache_key,
            "cache_kind": "patched",
            "object_keys": object_keys,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "writer_workflow": writer_workflow,
            "source_github_run_id": source_github_run_id,
            "source_ref": source_ref,
            "status": "pending",
        }
        self.cache_index[cid] = row
        return dict(row)

    def commit_cache_index_patched(
        self,
        *,
        cache_index_id: str,
        object_keys: dict[str, Any],
        sha256: str,
        size_bytes: int,
    ) -> dict[str, Any]:
        row = self.cache_index[cache_index_id]
        row.update(
            {
                "status": "committed",
                "object_keys": object_keys,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "committed_at_utc": "fake-ts",
            }
        )
        return dict(row)

    def list_patched_cache_rows(self) -> list[dict[str, Any]]:
        return [
            {"cache_key": r["cache_key"], "source_ref": r["source_ref"]}
            for r in self.cache_index.values()
            if r.get("cache_kind") == "patched" and r.get("status") == "committed"
        ]

    def get_patched_cache_row(self, *, cache_key: str) -> dict[str, Any] | None:
        row = self.get_cache_index_patched(cache_key=cache_key)
        if row is None or row.get("status") != "committed":
            return None
        return dict(row)

    def get_cache_index_patched(self, *, cache_key: str) -> dict[str, Any] | None:
        for row in self.cache_index.values():
            if row.get("cache_key") == cache_key and row.get("cache_kind") == "patched":
                return dict(row)
        return None

    def get_cache_pointer(self, *, cache_key: str) -> dict[str, Any] | None:
        row = self.cache_pointers.get(cache_key)
        return dict(row) if row else None


    def _orphan_rows_optional(self, table: str) -> list[dict[str, Any]]:
        try:
            resp = self._request(
                "GET",
                f"/rest/v1/{table}",
                params={"status": "eq.orphan", "select": "*"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Phase 4 tables may be absent until migration U-1 is applied.
            if exc.response.status_code in {400, 404}:
                return []
            raise
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        return rows

    def list_orphan_rows(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.artifact_index.values():
            if row.get("status") == "orphan":
                r = dict(row)
                r["_table"] = "artifact_index"
                out.append(r)
        for row in self.cache_index.values():
            if row.get("status") == "orphan":
                r = dict(row)
                r["_table"] = "cache_index"
                out.append(r)
        for row in self.monthly_snapshots.values():
            if row.get("status") == "orphan":
                r = dict(row)
                r["_table"] = "monthly_snapshots"
                out.append(r)
        for row in self.publish_status.values():
            if row.get("status") == "orphan":
                r = dict(row)
                r["_table"] = "publish_status"
                out.append(r)
        return out

    def insert_monthly_snapshot_pending(
        self,
        *,
        monthly_tag: str,
        snapshot_date: str,
        github_run_id: int,
        object_keys: dict[str, Any],
        sha256: str,
        writer_workflow: str = "monthly.yml",
    ) -> dict[str, Any]:
        for existing in self.monthly_snapshots.values():
            if existing.get("monthly_tag") == monthly_tag:
                if existing.get("status") == "committed":
                    return dict(existing)
                existing.update(
                    {
                        "snapshot_date": snapshot_date,
                        "github_run_id": github_run_id,
                        "writer_workflow": writer_workflow,
                        "object_keys": object_keys,
                        "sha256": sha256,
                        "status": "pending",
                    }
                )
                return dict(existing)
        sid = str(uuid4())
        row = {
            "id": sid,
            "monthly_tag": monthly_tag,
            "snapshot_date": snapshot_date,
            "github_run_id": github_run_id,
            "writer_workflow": writer_workflow,
            "object_keys": object_keys,
            "sha256": sha256,
            "status": "pending",
            "created_at_utc": "fake-ts",
        }
        self.monthly_snapshots[sid] = row
        return dict(row)

    def commit_monthly_snapshot(self, *, snapshot_id: str) -> dict[str, Any]:
        row = self.monthly_snapshots[snapshot_id]
        row["status"] = "committed"
        row["committed_at_utc"] = "fake-ts"
        return dict(row)

    def mark_monthly_snapshot_orphan(self, *, snapshot_id: str) -> None:
        self.monthly_snapshots[snapshot_id]["status"] = "orphan"

    def list_committed_monthly_tags(self) -> list[str]:
        rows = [
            r for r in self.monthly_snapshots.values() if r.get("status") == "committed"
        ]
        rows.sort(key=lambda r: (r.get("snapshot_date", ""), r.get("github_run_id", 0)), reverse=True)
        return [str(r["monthly_tag"]) for r in rows]

    def insert_publish_status_pending(
        self,
        *,
        run_id: str,
        workflow: str,
        github_run_id: int,
        run_date: str,
        logical_kind: str,
        visibility: str,
        object_key: str,
        manifest_object_key: str,
        size_bytes: int,
        sha256: str,
        content_type: str,
    ) -> dict[str, Any]:
        for existing in self.publish_status.values():
            if existing.get("run_id") == run_id and existing.get("logical_kind") == logical_kind:
                if existing.get("status") == "committed":
                    return dict(existing)
                existing.update(
                    {
                        "workflow": workflow,
                        "github_run_id": github_run_id,
                        "run_date": run_date,
                        "visibility": visibility,
                        "object_key": object_key,
                        "manifest_object_key": manifest_object_key,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "content_type": content_type,
                        "status": "pending",
                    }
                )
                return dict(existing)
        pid = str(uuid4())
        row = {
            "id": pid,
            "run_id": run_id,
            "workflow": workflow,
            "github_run_id": github_run_id,
            "run_date": run_date,
            "logical_kind": logical_kind,
            "visibility": visibility,
            "object_key": object_key,
            "manifest_object_key": manifest_object_key,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "content_type": content_type,
            "status": "pending",
            "created_at_utc": "fake-ts",
        }
        self.publish_status[pid] = row
        return dict(row)

    def commit_publish_status(self, *, publish_id: str) -> dict[str, Any]:
        row = self.publish_status[publish_id]
        row["status"] = "committed"
        row["committed_at_utc"] = "fake-ts"
        return dict(row)

    def mark_publish_status_orphan(self, *, publish_id: str) -> None:
        self.publish_status[publish_id]["status"] = "orphan"

    def get_publish_status(self, *, publish_id: str) -> dict[str, Any] | None:
        row = self.publish_status.get(publish_id)
        return dict(row) if row else None

    def commit_jpx_url_cache_rpc(
        self,
        *,
        object_key: str,
        sha256: str,
        size_bytes: int,
        writer_workflow: str,
        source_github_run_id: int,
        history_id: str | None,
    ) -> str:
        return self.commit_fixed_cache_rpc(
            cache_key="jpx-latest-url",
            object_key=object_key,
            sha256=sha256,
            size_bytes=size_bytes,
            writer_workflow=writer_workflow,
            source_github_run_id=source_github_run_id,
            history_id=history_id,
        )

    def delete_row(self, *, table: str, row_id: str) -> None:
        if table == "artifact_index":
            self.artifact_index.pop(row_id, None)
        elif table == "cache_index":
            self.cache_index.pop(row_id, None)
        elif table == "monthly_snapshots":
            self.monthly_snapshots.pop(row_id, None)
        elif table == "publish_status":
            self.publish_status.pop(row_id, None)

ENV_SUPABASE_CONTROL_FAKE = "SUPABASE_CONTROL_FAKE"


def control_adapter_from_env() -> SupabaseControlPort | None:
    """Return Fake or REST control-plane adapter from env; None if unconfigured."""
    if os.environ.get(ENV_SUPABASE_CONTROL_FAKE, "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    url = os.environ.get(ENV_SUPABASE_URL, "").strip()
    key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
    if not url or not key:
        return None
    return SupabaseRestAdapter.from_env()

