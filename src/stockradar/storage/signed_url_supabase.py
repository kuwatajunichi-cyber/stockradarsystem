"""Production REST adapters for Track B mint (service_role only)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

from stockradar.storage.signed_url import (
    MINT_DENIED,
    MINT_ISSUED,
    STATUS_COMMITTED,
    CommittedObjectRef,
    DownloadGrantRow,
)
from stockradar.storage.supabase_client import ENV_SUPABASE_SECRET_KEY, ENV_SUPABASE_URL

_OBJECT_KEY_TABLES: tuple[str, ...] = (
    "artifact_index",
    "cache_index",
    "publish_status",
    "derived_object_index",
)


def _sha_from_row(row: dict[str, Any]) -> str | None:
    for key in ("sha256", "byte_sha256"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def _size_from_row(row: dict[str, Any]) -> int | None:
    value = row.get("size_bytes")
    if value is None:
        return None
    return int(value)


@dataclass
class RestCommittedObjectResolver:
    url: str
    key: str
    _client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> RestCommittedObjectResolver:
        url = os.environ.get(ENV_SUPABASE_URL, "").strip().rstrip("/")
        key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
        if not url or not key:
            raise RuntimeError("Supabase configuration required for signed URL mint")
        return cls(url=url, key=key)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        if prefer:
            headers["Prefer"] = prefer
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        return self._client.request(
            method,
            f"{self.url}{path}",
            params=params,
            json=json_body,
            headers=headers,
        )

    def resolve(
        self,
        *,
        object_key: str | None,
        source_table: str | None,
        source_id: str | None,
    ) -> CommittedObjectRef | None:
        table = (source_table or "").strip() or None
        sid = (source_id or "").strip() or None
        key = (object_key or "").strip() or None
        if table and sid:
            return self._resolve_by_id(table, sid, expected_key=key)
        if key:
            return self._resolve_by_object_key(key)
        return None

    def _row_to_ref(self, table: str, row: dict[str, Any]) -> CommittedObjectRef:
        object_key = str(row.get("object_key") or "")
        if table == "monthly_snapshots" and not object_key:
            object_key = _monthly_object_key(row)
        return CommittedObjectRef(
            object_key=object_key,
            source_table=table,
            source_id=str(row.get("id") or ""),
            status=str(row.get("status") or ""),
            sha256=_sha_from_row(row),
            size_bytes=_size_from_row(row),
        )

    def _resolve_by_id(
        self,
        table: str,
        source_id: str,
        *,
        expected_key: str | None,
    ) -> CommittedObjectRef | None:
        resp = self._request(
            "GET",
            f"/rest/v1/{table}",
            params={"id": f"eq.{source_id}", "select": "*", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        ref = self._row_to_ref(table, rows[0])
        if expected_key and ref.object_key != expected_key:
            return None
        return ref

    def _resolve_by_object_key(self, object_key: str) -> CommittedObjectRef | None:
        hits: list[CommittedObjectRef] = []
        for table in _OBJECT_KEY_TABLES:
            resp = self._request(
                "GET",
                f"/rest/v1/{table}",
                params={
                    "object_key": f"eq.{object_key}",
                    "status": f"eq.{STATUS_COMMITTED}",
                    "select": "*",
                    "limit": "2",
                },
            )
            if resp.status_code in {400, 404}:
                continue
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list):
                continue
            for row in rows:
                hits.append(self._row_to_ref(table, row))
        if not hits:
            return None
        identities = {(h.source_table, h.source_id) for h in hits}
        if len(identities) > 1:
            return None
        return hits[0]


def _monthly_object_key(row: dict[str, Any]) -> str:
    keys = row.get("object_keys")
    if not isinstance(keys, dict):
        return ""
    core = keys.get("core")
    if isinstance(core, dict):
        return str(core.get("object_key") or "")
    return ""


@dataclass
class RestDownloadGrantsAudit:
    url: str
    key: str
    _client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> RestDownloadGrantsAudit:
        url = os.environ.get(ENV_SUPABASE_URL, "").strip().rstrip("/")
        key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
        if not url or not key:
            raise RuntimeError("Supabase configuration required for signed URL mint")
        return cls(url=url, key=key)

    def _request(
        self,
        method: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        if prefer:
            headers["Prefer"] = prefer
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        return self._client.request(
            method,
            f"{self.url}/rest/v1/download_grants",
            params=params,
            json=json_body,
            headers=headers,
        )

    def get_by_request_id(self, request_id: str) -> list[DownloadGrantRow]:
        resp = self._request(
            "GET",
            params={"request_id": f"eq.{request_id}", "select": "*"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        return [_grant_from_row(row) for row in rows if isinstance(row, dict)]

    def insert(self, row: DownloadGrantRow) -> DownloadGrantRow:
        resp = self._request(
            "POST",
            json_body=_grant_to_body(row),
            prefer="return=representation",
        )
        resp.raise_for_status()
        payload = resp.json()
        stored = payload[0] if isinstance(payload, list) else payload
        return _grant_from_row(stored)

    def update_issued(
        self,
        grant_id: str,
        *,
        expires_at_utc: str,
        ttl_seconds: int,
        sha256: str | None,
        object_key: str,
        source_table: str | None,
        source_id: str | None,
    ) -> DownloadGrantRow:
        body = {
            "expires_at_utc": expires_at_utc,
            "ttl_seconds": ttl_seconds,
            "sha256": sha256,
            "object_key": object_key,
            "source_table": source_table,
            "source_id": source_id,
            "mint_result": MINT_ISSUED,
            "reason_code": None,
        }
        resp = self._request(
            "PATCH",
            params={"id": f"eq.{grant_id}"},
            json_body=body,
            prefer="return=representation",
        )
        resp.raise_for_status()
        payload = resp.json()
        stored = payload[0] if isinstance(payload, list) else payload
        return _grant_from_row(stored)


def _grant_to_body(row: DownloadGrantRow) -> dict[str, Any]:
    return {
        "id": row.id or str(uuid4()),
        "created_at_utc": row.created_at_utc,
        "request_id": row.request_id,
        "object_key": row.object_key,
        "source_table": row.source_table,
        "source_id": row.source_id,
        "sha256": row.sha256,
        "actor_ref": row.actor_ref,
        "operation": row.operation,
        "ttl_seconds": row.ttl_seconds,
        "expires_at_utc": row.expires_at_utc,
        "mint_result": row.mint_result,
        "reason_code": row.reason_code,
    }


def _grant_from_row(row: dict[str, Any]) -> DownloadGrantRow:
    mint_result = str(row.get("mint_result") or MINT_DENIED)
    if mint_result not in {MINT_ISSUED, MINT_DENIED}:
        mint_result = MINT_DENIED
    return DownloadGrantRow(
        id=str(row.get("id") or ""),
        created_at_utc=str(row.get("created_at_utc") or ""),
        request_id=str(row.get("request_id") or ""),
        object_key=str(row.get("object_key") or ""),
        source_table=row.get("source_table"),
        source_id=str(row.get("source_id")) if row.get("source_id") else None,
        sha256=row.get("sha256"),
        actor_ref=str(row.get("actor_ref") or ""),
        operation=str(row.get("operation") or ""),
        ttl_seconds=int(row.get("ttl_seconds") or 0),
        expires_at_utc=row.get("expires_at_utc"),
        mint_result=mint_result,
        reason_code=row.get("reason_code"),
    )
