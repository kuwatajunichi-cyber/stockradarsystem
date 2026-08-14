"""Supabase derived generation adapter (Phase 4.5 migration 006 RPCs)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from stockradar.storage.derived_generation import (
    BeginGenerationRequest,
    GenerationConflictError,
    GenerationNotFoundError,
    GenerationRecord,
    LatestStagingRow,
    ObjectCoordinateConflictError,
    PendingObjectRecord,
    normalize_artifact_profile,
)
from stockradar.storage.supabase_client import (
    ENV_SUPABASE_SECRET_KEY,
    ENV_SUPABASE_URL,
    _auth_headers,
)


def _parse_utc(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    text = str(raw).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _map_generation_conflict(exc: httpx.HTTPStatusError) -> None:
    text = exc.response.text
    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "payload mismatch",
            "coordinate conflict",
            "mismatch",
            "not pending",
            "not all objects",
            "required for profile",
            "object count",
            "object_set_digest",
            "latest_set_digest",
            "new_digest mismatch",
        )
    ):
        raise GenerationConflictError(text) from exc
    if "coordinate conflict" in lowered:
        raise ObjectCoordinateConflictError(text) from exc


@dataclass
class SupabaseMetricGenerationAdapter:
    base_url: str
    secret_key: str
    writer_workflow: str = "derived_writer.yml"
    run_attempt: int = 1
    source_run_id: str | None = None
    timeout_s: float = 30.0
    _object_ids_by_key: dict[tuple[str, str], str] = field(default_factory=dict)
    _metric_set_by_generation: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> SupabaseMetricGenerationAdapter:
        url = os.environ.get(ENV_SUPABASE_URL, "").strip().rstrip("/")
        key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
        if not url or not key:
            raise RuntimeError(f"{ENV_SUPABASE_URL} and {ENV_SUPABASE_SECRET_KEY} are required")
        workflow = os.environ.get("GITHUB_WORKFLOW", "derived_writer.yml").strip() or "derived_writer.yml"
        attempt_raw = os.environ.get("GITHUB_RUN_ATTEMPT", "1").strip() or "1"
        try:
            run_attempt = int(attempt_raw)
        except ValueError:
            run_attempt = 1
        source_run_id = os.environ.get("SUPABASE_SOURCE_RUN_ID", "").strip() or None
        return cls(
            base_url=url,
            secret_key=key,
            writer_workflow=workflow,
            run_attempt=run_attempt,
            source_run_id=source_run_id,
        )

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

    def _rpc(self, name: str, body: dict[str, Any]) -> Any:
        resp = self._request("POST", f"/rest/v1/rpc/{name}", json_body=body)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _map_generation_conflict(exc)
            raise
        if not resp.content:
            return None
        return resp.json()

    def _fetch_generation_row(self, generation_id: str) -> dict[str, Any]:
        resp = self._request(
            "GET",
            "/rest/v1/derived_generation_runs",
            params={"id": f"eq.{generation_id}", "select": "*"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            raise GenerationNotFoundError(f"generation not found: {generation_id!r}")
        return rows[0]

    def _to_generation_record(self, row: dict[str, Any]) -> GenerationRecord:
        trade_date = row.get("trade_date")
        trade_date_str = str(trade_date) if trade_date is not None else ""
        return GenerationRecord(
            generation_id=str(row["id"]),
            metric_set_version_id=str(row["metric_set_version_id"]),
            trade_date=trade_date_str,
            mode=str(row["mode"]),
            artifact_profile=str(row["artifact_profile"]),
            repository=str(row["repository"]),
            workflow=str(row["workflow"]),
            github_run_id=int(row["github_run_id"]),
            status=str(row["status"]),
            expected_logical_digest=row.get("expected_old_digest"),
            new_logical_digest=row.get("new_digest") or row.get("declared_new_digest"),
            heartbeat_at=_parse_utc(row.get("heartbeat_at")),
            created_at_utc=_parse_utc(row.get("created_at_utc")),
            committed_at_utc=_parse_utc(row.get("committed_at_utc"))
            if row.get("committed_at_utc")
            else None,
        )

    def begin_generation(self, request: BeginGenerationRequest) -> GenerationRecord:
        source = request.source
        profile = normalize_artifact_profile(request.artifact_profile)
        body: dict[str, Any] = {
            "p_metric_set_version_id": source.metric_set_version_id.strip(),
            "p_trade_date": source.trade_date.strip(),
            "p_mode": str(source.mode),
            "p_artifact_profile": profile,
            "p_repository": source.repository.strip(),
            "p_workflow": source.workflow.strip(),
            "p_github_run_id": int(source.github_run_id),
            "p_run_attempt": self.run_attempt,
            "p_writer_workflow": self.writer_workflow,
            "p_source_run_id": self.source_run_id,
            "p_expected_old_digest": request.expected_logical_digest,
            "p_declared_new_digest": request.new_logical_digest,
            "p_expected_object_count": request.expected_object_count,
            "p_expected_object_set_digest": request.expected_object_set_digest,
            "p_expected_latest_set_digest": request.expected_latest_set_digest,
        }
        generation_id = str(self._rpc("begin_derived_generation", body))
        self._metric_set_by_generation[generation_id] = source.metric_set_version_id.strip()
        return self._to_generation_record(self._fetch_generation_row(generation_id))

    def register_pending_object(
        self,
        *,
        generation_id: str,
        object_kind: str,
        object_key: str,
        logical_digest: str,
        byte_sha256: str,
        size_bytes: int,
        trade_date: str | None = None,
        instrument_code: str | None = None,
        series_year: int | None = None,
        layer1_input_fingerprint: str | None = None,
    ) -> PendingObjectRecord:
        body: dict[str, Any] = {
            "p_generation_id": generation_id,
            "p_object_kind": object_kind.strip().lower(),
            "p_object_key": object_key.strip(),
            "p_logical_digest": logical_digest.strip().lower(),
            "p_layer1_input_fingerprint": layer1_input_fingerprint,
            "p_writer_workflow": self.writer_workflow,
            "p_trade_date": trade_date,
            "p_instrument_code": instrument_code,
            "p_series_year": series_year,
        }
        object_id = str(self._rpc("register_pending_derived_object", body))
        key = (generation_id, object_key.strip())
        self._object_ids_by_key[key] = object_id
        return PendingObjectRecord(
            object_id=object_id,
            generation_id=generation_id,
            object_kind=object_kind.strip().lower(),
            object_key=object_key.strip(),
            logical_digest=logical_digest.strip().lower(),
            byte_sha256=byte_sha256.strip().lower(),
            size_bytes=int(size_bytes),
            trade_date=trade_date,
            instrument_code=instrument_code,
            series_year=series_year,
            layer1_input_fingerprint=layer1_input_fingerprint,
            upload_verified_at=None,
        )

    def mark_object_uploaded(
        self,
        *,
        generation_id: str,
        object_key: str,
        byte_sha256: str,
        size_bytes: int,
    ) -> PendingObjectRecord:
        key = (generation_id, object_key.strip())
        object_id = self._object_ids_by_key.get(key)
        if object_id is None:
            pending = self.list_pending_objects(generation_id)
            for row in pending:
                if row.object_key == object_key.strip():
                    object_id = row.object_id
                    self._object_ids_by_key[key] = object_id
                    break
        if object_id is None:
            raise GenerationNotFoundError(f"pending object not found: {object_key!r}")

        body = {
            "p_object_id": object_id,
            "p_byte_sha256": byte_sha256.strip().lower(),
            "p_size_bytes": int(size_bytes),
        }
        self._rpc("mark_derived_object_uploaded", body)
        for row in self.list_pending_objects(generation_id):
            if row.object_id == object_id:
                return row
        raise GenerationNotFoundError(f"pending object not found after upload: {object_key!r}")

    def stage_latest_observation(
        self,
        *,
        generation_id: str,
        instrument_code: str,
        trade_date: str,
        values_json: dict[str, Any],
        logical_digest: str,
    ) -> LatestStagingRow:
        metric_set_version_id = self._metric_set_by_generation.get(generation_id)
        if metric_set_version_id is None:
            row = self._fetch_generation_row(generation_id)
            metric_set_version_id = str(row["metric_set_version_id"])
            self._metric_set_by_generation[generation_id] = metric_set_version_id

        body = {
            "generation_id": generation_id,
            "instrument_code": instrument_code.strip(),
            "metric_set_version_id": metric_set_version_id,
            "trade_date": trade_date.strip(),
            "values_json": values_json,
            "logical_digest": logical_digest.strip().lower(),
            "source_run_id": self.source_run_id,
        }
        resp = self._request(
            "POST",
            "/rest/v1/latest_derived_observations_staging",
            json_body=body,
            prefer="resolution=merge-duplicates,return=representation",
            params={"on_conflict": "generation_id,instrument_code"},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _map_generation_conflict(exc)
            raise
        return LatestStagingRow(
            generation_id=generation_id,
            instrument_code=instrument_code.strip(),
            trade_date=trade_date.strip(),
            values_json=dict(values_json),
            logical_digest=logical_digest.strip().lower(),
        )

    def heartbeat(self, *, generation_id: str) -> GenerationRecord:
        self._rpc("heartbeat_derived_generation", {"p_generation_id": generation_id})
        return self._to_generation_record(self._fetch_generation_row(generation_id))

    def commit_generation(
        self,
        *,
        generation_id: str,
        new_logical_digest: str,
        expected_old_digest: str | None = None,
    ) -> GenerationRecord:
        if expected_old_digest is not None:
            row = self._fetch_generation_row(generation_id)
            current = row.get("expected_old_digest")
            expected = expected_old_digest.strip().lower()
            if current is not None and str(current).strip().lower() != expected:
                raise GenerationConflictError(
                    f"expected_old_digest mismatch: current={current!r} expected={expected!r}"
                )
        self._rpc(
            "commit_derived_generation",
            {
                "p_generation_id": generation_id,
                "p_new_digest": new_logical_digest.strip().lower(),
            },
        )
        return self._to_generation_record(self._fetch_generation_row(generation_id))

    def fail_generation(self, *, generation_id: str, reason: str) -> GenerationRecord:
        self._rpc("mark_derived_generation_failed", {"p_generation_id": generation_id})
        return self._to_generation_record(self._fetch_generation_row(generation_id))

    def list_stale_generations(
        self,
        *,
        stale_after: timedelta,
        now_utc: datetime | None = None,
    ) -> list[GenerationRecord]:
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        stale_before = (now - stale_after).isoformat()
        resp = self._request(
            "POST",
            "/rest/v1/rpc/list_stale_derived_generations",
            json_body={"p_stale_before": stale_before},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        return [self._to_generation_record(row) for row in rows]

    def get_generation(self, generation_id: str) -> GenerationRecord | None:
        resp = self._request(
            "GET",
            "/rest/v1/derived_generation_runs",
            params={"id": f"eq.{generation_id}", "select": "*"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        return self._to_generation_record(rows[0])

    def list_pending_objects(self, generation_id: str) -> list[PendingObjectRecord]:
        resp = self._request(
            "GET",
            "/rest/v1/derived_object_index",
            params={
                "generation_id": f"eq.{generation_id}",
                "status": "eq.pending",
                "select": "*",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        pending: list[PendingObjectRecord] = []
        for row in rows:
            object_id = str(row["id"])
            object_key = str(row["object_key"])
            self._object_ids_by_key[(generation_id, object_key)] = object_id
            upload_verified = row.get("upload_verified_at")
            pending.append(
                PendingObjectRecord(
                    object_id=object_id,
                    generation_id=generation_id,
                    object_kind=str(row["object_kind"]),
                    object_key=object_key,
                    logical_digest=str(row["logical_digest"]),
                    byte_sha256=str(row.get("byte_sha256") or ""),
                    size_bytes=int(row.get("size_bytes") or 0),
                    trade_date=row.get("trade_date"),
                    instrument_code=row.get("instrument_code"),
                    series_year=row.get("series_year"),
                    layer1_input_fingerprint=row.get("layer1_input_fingerprint"),
                    upload_verified_at=_parse_utc(upload_verified) if upload_verified else None,
                )
            )
        pending.sort(key=lambda item: item.object_key)
        return pending
