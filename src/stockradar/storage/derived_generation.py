"""Phase 4.5 derived generation control-plane Protocol + Fake (Issue #93)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

from stockradar.storage.phase4_5_rollout import RunMode, normalize_run_mode


class ArtifactProfile(str, Enum):
    SNAPSHOT_ONLY = "snapshot_only"
    SNAPSHOT_SERIES = "snapshot_series"
    SNAPSHOT_SERIES_LATEST = "snapshot_series_latest"


VALID_ARTIFACT_PROFILES: frozenset[str] = frozenset(p.value for p in ArtifactProfile)


class GenerationStatus(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


class GenerationConflictError(RuntimeError):
    """Generation identity or payload mismatch — exit 2 contract."""


class GenerationNotFoundError(RuntimeError):
    """Unknown generation or pending object row."""


class ObjectCoordinateConflictError(RuntimeError):
    """Same logical coordinate reserved with different byte hash."""


@dataclass(frozen=True)
class SourceRunIdentity:
    repository: str
    workflow: str
    github_run_id: int
    metric_set_version_id: str
    trade_date: str
    mode: RunMode

    def key(self) -> tuple[str, str, int, str, str, str]:
        return (
            self.repository.strip(),
            self.workflow.strip(),
            int(self.github_run_id),
            self.metric_set_version_id.strip().lower(),
            self.trade_date.strip(),
            normalize_run_mode(self.mode),
        )


@dataclass(frozen=True)
class BeginGenerationRequest:
    source: SourceRunIdentity
    artifact_profile: ArtifactProfile | str
    expected_logical_digest: str | None = None
    new_logical_digest: str | None = None
    expected_object_count: int | None = None
    expected_object_set_digest: str | None = None
    expected_latest_row_count: int | None = None
    expected_latest_set_digest: str | None = None


@dataclass(frozen=True)
class GenerationRecord:
    generation_id: str
    metric_set_version_id: str
    trade_date: str
    mode: str
    artifact_profile: str
    repository: str
    workflow: str
    github_run_id: int
    status: str
    expected_logical_digest: str | None
    new_logical_digest: str | None
    heartbeat_at: datetime
    created_at_utc: datetime
    committed_at_utc: datetime | None = None


@dataclass(frozen=True)
class PendingObjectRecord:
    object_id: str
    generation_id: str
    object_kind: str
    object_key: str
    logical_digest: str
    byte_sha256: str
    size_bytes: int
    trade_date: str | None = None
    instrument_code: str | None = None
    series_year: int | None = None
    layer1_input_fingerprint: str | None = None
    upload_verified_at: datetime | None = None


@dataclass(frozen=True)
class LatestStagingRow:
    generation_id: str
    instrument_code: str
    trade_date: str
    values_json: dict[str, Any]
    logical_digest: str


class MetricGenerationPort(Protocol):
    def begin_generation(self, request: BeginGenerationRequest) -> GenerationRecord: ...

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
    ) -> PendingObjectRecord: ...

    def mark_object_uploaded(
        self,
        *,
        generation_id: str,
        object_key: str,
        byte_sha256: str,
        size_bytes: int,
    ) -> PendingObjectRecord: ...

    def stage_latest_observation(
        self,
        *,
        generation_id: str,
        instrument_code: str,
        trade_date: str,
        values_json: dict[str, Any],
        logical_digest: str,
    ) -> LatestStagingRow: ...

    def heartbeat(self, *, generation_id: str) -> GenerationRecord: ...

    def commit_generation(
        self,
        *,
        generation_id: str,
        new_logical_digest: str,
        expected_old_digest: str | None = None,
    ) -> GenerationRecord: ...

    def fail_generation(self, *, generation_id: str, reason: str) -> GenerationRecord: ...

    def list_stale_generations(
        self,
        *,
        stale_after: timedelta,
        now_utc: datetime | None = None,
    ) -> list[GenerationRecord]: ...

    def get_generation(self, generation_id: str) -> GenerationRecord | None: ...

    def list_pending_objects(self, generation_id: str) -> list[PendingObjectRecord]: ...


def normalize_artifact_profile(raw: str | ArtifactProfile) -> str:
    if isinstance(raw, ArtifactProfile):
        return raw.value
    profile = str(raw or "").strip().lower()
    if profile not in VALID_ARTIFACT_PROFILES:
        raise ValueError(f"invalid artifact profile: {raw!r}")
    return profile


def resolve_artifact_profile(
    *,
    stage: str,
    mode: RunMode,
    is_current_latest_trade_date: bool = False,
) -> ArtifactProfile:
    """Map rollout stage/mode to generation artifact profile (plan SSOT)."""
    normalized_mode = normalize_run_mode(mode)
    normalized_stage = stage.strip().lower()
    if normalized_mode == "reconcile":
        if is_current_latest_trade_date:
            return ArtifactProfile.SNAPSHOT_SERIES_LATEST
        return ArtifactProfile.SNAPSHOT_SERIES
    if normalized_mode == "backfill" or normalized_stage in {"4.5a", "4.5b"}:
        if normalized_stage == "4.5a":
            return ArtifactProfile.SNAPSHOT_ONLY
        return ArtifactProfile.SNAPSHOT_SERIES
    if normalized_stage == "4.5c":
        return ArtifactProfile.SNAPSHOT_SERIES_LATEST
    raise ValueError(f"cannot resolve artifact profile for stage={stage!r} mode={mode!r}")


def profile_allows_series(profile: str | ArtifactProfile) -> bool:
    normalized = normalize_artifact_profile(profile)
    return normalized in {
        ArtifactProfile.SNAPSHOT_SERIES.value,
        ArtifactProfile.SNAPSHOT_SERIES_LATEST.value,
    }


def profile_allows_latest(profile: str | ArtifactProfile) -> bool:
    return normalize_artifact_profile(profile) == ArtifactProfile.SNAPSHOT_SERIES_LATEST.value


def _utc_now(now_utc: datetime | None = None) -> datetime:
    if now_utc is None:
        return datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        return now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(timezone.utc)


def _object_coordinate_key(
    *,
    object_kind: str,
    object_key: str,
    trade_date: str | None,
    instrument_code: str | None,
    series_year: int | None,
) -> tuple[str, str, str | None, str | None, int | None]:
    return (
        object_kind.strip().lower(),
        object_key.strip(),
        trade_date,
        instrument_code,
        series_year,
    )


@dataclass
class FakeMetricGenerationStore:
  """In-memory generation store for Secrets-free tests."""

  generations: dict[str, dict[str, Any]] = field(default_factory=dict)
  pending_objects: dict[str, dict[str, Any]] = field(default_factory=dict)
  latest_staging: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
  committed_snapshot_digest_by_set_date: dict[tuple[str, str], str] = field(default_factory=dict)
  identity_index: dict[tuple[str, ...], str] = field(default_factory=dict)
  _clock: datetime | None = None

  def _now(self) -> datetime:
    return _utc_now(self._clock)

  def begin_generation(self, request: BeginGenerationRequest) -> GenerationRecord:
    source = request.source
    identity_key = source.key()
    profile = normalize_artifact_profile(request.artifact_profile)
    now = self._now()

    existing_id = self.identity_index.get(identity_key)
    if existing_id is not None:
      row = self.generations[existing_id]
      status = str(row["status"])
      if status == GenerationStatus.COMMITTED.value:
        if (
          request.new_logical_digest
          and row.get("new_logical_digest") == request.new_logical_digest
        ):
          return self._to_generation_record(row)
        raise GenerationConflictError(
          f"committed generation {existing_id!r} cannot be restarted with different payload"
        )
      if status == GenerationStatus.FAILED.value:
        raise GenerationConflictError(f"generation {existing_id!r} is failed")
      row["heartbeat_at"] = now
      return self._to_generation_record(row)

    generation_id = str(uuid4())
    row = {
      "generation_id": generation_id,
      "metric_set_version_id": source.metric_set_version_id.strip().lower(),
      "trade_date": source.trade_date.strip(),
      "mode": normalize_run_mode(source.mode),
      "artifact_profile": profile,
      "repository": source.repository.strip(),
      "workflow": source.workflow.strip(),
      "github_run_id": int(source.github_run_id),
      "status": GenerationStatus.PENDING.value,
      "expected_logical_digest": request.expected_logical_digest,
      "new_logical_digest": request.new_logical_digest,
      "expected_object_count": request.expected_object_count,
      "expected_object_set_digest": request.expected_object_set_digest,
      "expected_latest_row_count": request.expected_latest_row_count,
      "expected_latest_set_digest": request.expected_latest_set_digest,
      "heartbeat_at": now,
      "created_at_utc": now,
      "committed_at_utc": None,
    }
    self.generations[generation_id] = row
    self.identity_index[identity_key] = generation_id
    return self._to_generation_record(row)

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
    generation = self._require_pending_generation(generation_id)
    coord = _object_coordinate_key(
      object_kind=object_kind,
      object_key=object_key,
      trade_date=trade_date,
      instrument_code=instrument_code,
      series_year=series_year,
    )
    for existing in self.pending_objects.values():
      if existing["generation_id"] != generation_id:
        continue
      existing_coord = _object_coordinate_key(
        object_kind=str(existing["object_kind"]),
        object_key=str(existing["object_key"]),
        trade_date=existing.get("trade_date"),
        instrument_code=existing.get("instrument_code"),
        series_year=existing.get("series_year"),
      )
      if existing_coord != coord:
        continue
      if (
        existing["byte_sha256"] == byte_sha256.strip().lower()
        and int(existing["size_bytes"]) == int(size_bytes)
      ):
        return self._to_pending_object_record(existing)
      raise ObjectCoordinateConflictError(
        f"coordinate {coord!r} already reserved with different bytes"
      )

    object_id = str(uuid4())
    row = {
      "object_id": object_id,
      "generation_id": generation_id,
      "object_kind": object_kind.strip().lower(),
      "object_key": object_key.strip(),
      "logical_digest": logical_digest.strip().lower(),
      "byte_sha256": byte_sha256.strip().lower(),
      "size_bytes": int(size_bytes),
      "trade_date": trade_date,
      "instrument_code": instrument_code,
      "series_year": series_year,
      "layer1_input_fingerprint": layer1_input_fingerprint,
      "upload_verified_at": None,
      "status": "pending",
      "metric_set_version_id": generation["metric_set_version_id"],
    }
    self.pending_objects[object_id] = row
    return self._to_pending_object_record(row)

  def mark_object_uploaded(
    self,
    *,
    generation_id: str,
    object_key: str,
    byte_sha256: str,
    size_bytes: int,
  ) -> PendingObjectRecord:
    self._require_pending_generation(generation_id)
    digest = byte_sha256.strip().lower()
    size = int(size_bytes)
    for row in self.pending_objects.values():
      if row["generation_id"] != generation_id:
        continue
      if row["object_key"] != object_key.strip():
        continue
      if row["byte_sha256"] != digest or int(row["size_bytes"]) != size:
        raise GenerationConflictError(
          f"uploaded bytes mismatch for {object_key!r}"
        )
      row["upload_verified_at"] = self._now()
      return self._to_pending_object_record(row)
    raise GenerationNotFoundError(f"pending object not found: {object_key!r}")

  def stage_latest_observation(
    self,
    *,
    generation_id: str,
    instrument_code: str,
    trade_date: str,
    values_json: dict[str, Any],
    logical_digest: str,
  ) -> LatestStagingRow:
    generation = self._require_pending_generation(generation_id)
    if not profile_allows_latest(str(generation["artifact_profile"])):
      raise GenerationConflictError(
        f"profile {generation['artifact_profile']!r} does not allow latest staging"
      )
    key = (generation_id, instrument_code.strip())
    row = {
      "generation_id": generation_id,
      "instrument_code": instrument_code.strip(),
      "trade_date": trade_date.strip(),
      "values_json": dict(values_json),
      "logical_digest": logical_digest.strip().lower(),
    }
    self.latest_staging[key] = row
    return LatestStagingRow(**row)

  def heartbeat(self, *, generation_id: str) -> GenerationRecord:
    row = self._require_generation(generation_id)
    if row["status"] != GenerationStatus.PENDING.value:
      return self._to_generation_record(row)
    row["heartbeat_at"] = self._now()
    return self._to_generation_record(row)

  def commit_generation(
    self,
    *,
    generation_id: str,
    new_logical_digest: str,
    expected_old_digest: str | None = None,
  ) -> GenerationRecord:
    generation = self._require_pending_generation(generation_id)
    profile = str(generation["artifact_profile"])
    digest = new_logical_digest.strip().lower()
    set_id = str(generation["metric_set_version_id"])
    trade_date = str(generation["trade_date"])

    if expected_old_digest is not None:
      current = self.committed_snapshot_digest_by_set_date.get((set_id, trade_date))
      expected = expected_old_digest.strip().lower()
      if current is not None and current != expected:
        raise GenerationConflictError(
          f"expected_old_digest mismatch: current={current!r} expected={expected!r}"
        )

    objects = [
      row
      for row in self.pending_objects.values()
      if row["generation_id"] == generation_id
    ]
    if not objects:
      raise GenerationConflictError("commit requires at least one pending object")
    for row in objects:
      if row.get("upload_verified_at") is None:
        raise GenerationConflictError(
          f"object not uploaded: {row['object_key']!r}"
        )

    has_series = any(row["object_kind"] == "series" for row in objects)
    has_snapshot = any(row["object_kind"] == "snapshot" for row in objects)
    if profile == ArtifactProfile.SNAPSHOT_ONLY.value and has_series:
      raise GenerationConflictError("snapshot_only profile rejects series objects")
    if profile != ArtifactProfile.SNAPSHOT_SERIES_LATEST.value and self._latest_rows(generation_id):
      raise GenerationConflictError("latest staging not allowed for profile")
    if profile == ArtifactProfile.SNAPSHOT_SERIES_LATEST.value and not has_snapshot:
      raise GenerationConflictError("snapshot_series_latest requires snapshot object")

    expected_count = generation.get("expected_object_count")
    if expected_count is not None and int(expected_count) != len(objects):
      raise GenerationConflictError("expected_object_count mismatch")

    now = self._now()
    generation["status"] = GenerationStatus.COMMITTED.value
    generation["new_logical_digest"] = digest
    generation["committed_at_utc"] = now
    generation["heartbeat_at"] = now
    for row in objects:
      row["status"] = "committed"
    if has_snapshot:
      self.committed_snapshot_digest_by_set_date[(set_id, trade_date)] = digest
    return self._to_generation_record(generation)

  def fail_generation(self, *, generation_id: str, reason: str) -> GenerationRecord:
    generation = self._require_generation(generation_id)
    if generation["status"] != GenerationStatus.PENDING.value:
      raise GenerationConflictError(
        f"cannot fail generation in status {generation['status']!r}"
      )
    generation["status"] = GenerationStatus.FAILED.value
    generation["failure_reason"] = reason
    generation["heartbeat_at"] = self._now()
    for row in self.pending_objects.values():
      if row["generation_id"] == generation_id:
        row["status"] = "orphan"
    for key in list(self.latest_staging):
      if key[0] == generation_id:
        del self.latest_staging[key]
    return self._to_generation_record(generation)

  def list_stale_generations(
    self,
    *,
    stale_after: timedelta,
    now_utc: datetime | None = None,
  ) -> list[GenerationRecord]:
    now = _utc_now(now_utc or self._clock)
    cutoff = now - stale_after
    stale: list[GenerationRecord] = []
    for row in self.generations.values():
      if row["status"] != GenerationStatus.PENDING.value:
        continue
      heartbeat = row["heartbeat_at"]
      if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
      if heartbeat <= cutoff:
        stale.append(self._to_generation_record(row))
    stale.sort(key=lambda item: item.generation_id)
    return stale

  def get_generation(self, generation_id: str) -> GenerationRecord | None:
    row = self.generations.get(generation_id)
    if row is None:
      return None
    return self._to_generation_record(row)

  def list_pending_objects(self, generation_id: str) -> list[PendingObjectRecord]:
    rows = [
      row
      for row in self.pending_objects.values()
      if row["generation_id"] == generation_id
    ]
    rows.sort(key=lambda row: str(row["object_key"]))
    return [self._to_pending_object_record(row) for row in rows]

  def _latest_rows(self, generation_id: str) -> list[LatestStagingRow]:
    return [
      LatestStagingRow(**row)
      for key, row in self.latest_staging.items()
      if key[0] == generation_id
    ]

  def _require_generation(self, generation_id: str) -> dict[str, Any]:
    row = self.generations.get(generation_id)
    if row is None:
      raise GenerationNotFoundError(f"generation not found: {generation_id!r}")
    return row

  def _require_pending_generation(self, generation_id: str) -> dict[str, Any]:
    row = self._require_generation(generation_id)
    if row["status"] != GenerationStatus.PENDING.value:
      raise GenerationConflictError(
        f"generation {generation_id!r} is not pending (status={row['status']!r})"
      )
    return row

  @staticmethod
  def _to_generation_record(row: dict[str, Any]) -> GenerationRecord:
    return GenerationRecord(
      generation_id=str(row["generation_id"]),
      metric_set_version_id=str(row["metric_set_version_id"]),
      trade_date=str(row["trade_date"]),
      mode=str(row["mode"]),
      artifact_profile=str(row["artifact_profile"]),
      repository=str(row["repository"]),
      workflow=str(row["workflow"]),
      github_run_id=int(row["github_run_id"]),
      status=str(row["status"]),
      expected_logical_digest=row.get("expected_logical_digest"),
      new_logical_digest=row.get("new_logical_digest"),
      heartbeat_at=row["heartbeat_at"],
      created_at_utc=row["created_at_utc"],
      committed_at_utc=row.get("committed_at_utc"),
    )

  @staticmethod
  def _to_pending_object_record(row: dict[str, Any]) -> PendingObjectRecord:
    return PendingObjectRecord(
      object_id=str(row["object_id"]),
      generation_id=str(row["generation_id"]),
      object_kind=str(row["object_kind"]),
      object_key=str(row["object_key"]),
      logical_digest=str(row["logical_digest"]),
      byte_sha256=str(row["byte_sha256"]),
      size_bytes=int(row["size_bytes"]),
      trade_date=row.get("trade_date"),
      instrument_code=row.get("instrument_code"),
      series_year=row.get("series_year"),
      layer1_input_fingerprint=row.get("layer1_input_fingerprint"),
      upload_verified_at=row.get("upload_verified_at"),
    )


def compute_object_set_digest(object_keys: list[str]) -> str:
    """Sorted object-key set digest for generation commit validation."""
    normalized = sorted(key.strip() for key in object_keys)
    payload = "\n".join(normalized).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
