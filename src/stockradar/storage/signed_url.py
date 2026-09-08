"""Track B signed URL capability: fail-closed GetObject mint (Protocol + Fake)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import uuid4

KNOWN_OBJECT_PREFIXES: tuple[str, ...] = (
    "published/",
    "runs/",
    "cache/",
    "monthly/",
    "derived-snapshots/",
    "derived-series/",
    "derived-inputs/",
    "0011_work/",
    "0012_paid/",
)

ALLOWED_SOURCE_TABLES: frozenset[str] = frozenset(
    {
        "artifact_index",
        "cache_index",
        "publish_status",
        "derived_object_index",
        "monthly_snapshots",
    }
)

TTL_DEFAULT_SECONDS = 300
TTL_MIN_SECONDS = 60
TTL_MAX_SECONDS = 3600
OPERATION_GET_OBJECT = "GetObject"

MINT_ISSUED = "issued"
MINT_DENIED = "denied"

REASON_ENTITLEMENT_UNPROVEN = "entitlement_unproven"
REASON_ENTITLEMENT_DENIED = "entitlement_denied"
REASON_NOT_COMMITTED = "not_committed"
REASON_ORPHAN = "orphan"
REASON_OBJECT_MISSING = "object_missing"
REASON_IDENTITY_MISMATCH = "identity_mismatch"
REASON_CHECKSUM_MISMATCH = "checksum_mismatch"
REASON_PREFIX_REJECTED = "prefix_rejected"
REASON_TTL_INVALID = "ttl_invalid"
REASON_OPERATION_REJECTED = "operation_rejected"
REASON_PUBLIC_BUCKET_FORBIDDEN = "public_bucket_forbidden"
REASON_REQUEST_ID_CONFLICT = "request_id_conflict"

PROOF_PROVEN = "proven"
PROOF_UNPROVEN = "unproven"
PROOF_DENIED = "denied"

STATUS_COMMITTED = "committed"
STATUS_PENDING = "pending"
STATUS_ORPHAN = "orphan"

_REASON_CODES: frozenset[str] = frozenset(
    {
        REASON_ENTITLEMENT_UNPROVEN,
        REASON_ENTITLEMENT_DENIED,
        REASON_NOT_COMMITTED,
        REASON_ORPHAN,
        REASON_OBJECT_MISSING,
        REASON_IDENTITY_MISMATCH,
        REASON_CHECKSUM_MISMATCH,
        REASON_PREFIX_REJECTED,
        REASON_TTL_INVALID,
        REASON_OPERATION_REJECTED,
        REASON_PUBLIC_BUCKET_FORBIDDEN,
        REASON_REQUEST_ID_CONFLICT,
    }
)


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CommittedObjectRef:
    object_key: str
    source_table: str
    source_id: str
    status: str
    sha256: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True)
class DownloadGrantRow:
    id: str
    created_at_utc: str
    request_id: str
    object_key: str
    source_table: str | None
    source_id: str | None
    sha256: str | None
    actor_ref: str
    operation: str
    ttl_seconds: int
    expires_at_utc: str | None
    mint_result: str
    reason_code: str | None


@dataclass(frozen=True)
class MintRequest:
    request_id: str
    actor_ref: str
    operation: str = OPERATION_GET_OBJECT
    object_key: str | None = None
    source_table: str | None = None
    source_id: str | None = None
    ttl_seconds: int = TTL_DEFAULT_SECONDS


@dataclass(frozen=True)
class MintOutcome:
    exit_code: int
    mint_result: str
    reason_code: str | None
    grant_id: str | None
    object_key: str | None
    expires_at_utc: str | None
    signed_url: str | None
    request_id: str | None = None

    def public_dict(self) -> dict[str, object]:
        """Observability payload: never includes the signed URL body."""
        return {
            "exit_code": self.exit_code,
            "mint_result": self.mint_result,
            "reason_code": self.reason_code,
            "grant_id": self.grant_id,
            "object_key": self.object_key,
            "expires_at_utc": self.expires_at_utc,
            "request_id": self.request_id,
            "signed_url_present": bool(self.signed_url),
        }

    def caller_dict(self) -> dict[str, object]:
        payload = self.public_dict()
        if self.signed_url:
            payload["signed_url"] = self.signed_url
        return payload


class EntitlementProofPort(Protocol):
    def prove(self, *, actor_ref: str, object_key: str) -> str: ...


class CommittedObjectResolverPort(Protocol):
    def resolve(
        self,
        *,
        object_key: str | None,
        source_table: str | None,
        source_id: str | None,
    ) -> CommittedObjectRef | None: ...


class DownloadGrantsAuditPort(Protocol):
    def get_by_request_id(self, request_id: str) -> list[DownloadGrantRow]: ...

    def insert(self, row: DownloadGrantRow) -> DownloadGrantRow: ...

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
    ) -> DownloadGrantRow: ...


class R2HeadAndPresignPort(Protocol):
    def head_object(self, object_key: str) -> object: ...

    def presign_get_object(self, object_key: str, *, ttl_seconds: int) -> str: ...

    def delivery_bucket_is_public(self) -> bool: ...


class SignedUrlMintPort(Protocol):
    def mint_get(self, request: MintRequest) -> MintOutcome: ...


@dataclass
class FixedEntitlementProof:
    """Test/smoke fixture. Default is unproven (allow-stub forbidden)."""

    status: str = PROOF_UNPROVEN

    def prove(self, *, actor_ref: str, object_key: str) -> str:
        _ = actor_ref, object_key
        if self.status not in {PROOF_PROVEN, PROOF_UNPROVEN, PROOF_DENIED}:
            return PROOF_UNPROVEN
        return self.status


@dataclass
class FakeCommittedObjectResolver:
    objects: list[CommittedObjectRef] = field(default_factory=list)

    def add(self, ref: CommittedObjectRef) -> None:
        self.objects.append(ref)

    def resolve(
        self,
        *,
        object_key: str | None,
        source_table: str | None,
        source_id: str | None,
    ) -> CommittedObjectRef | None:
        key = (object_key or "").strip() or None
        table = (source_table or "").strip() or None
        sid = (source_id or "").strip() or None
        if table and table not in ALLOWED_SOURCE_TABLES:
            return None
        hits: list[CommittedObjectRef] = []
        for ref in self.objects:
            if key and ref.object_key != key:
                continue
            if table and ref.source_table != table:
                continue
            if sid and ref.source_id != sid:
                continue
            if key or (table and sid):
                hits.append(ref)
        if not hits:
            return None
        if len(hits) > 1:
            keys = {h.object_key for h in hits}
            ids = {(h.source_table, h.source_id) for h in hits}
            if len(keys) > 1 or len(ids) > 1:
                return None
        return hits[0]


@dataclass
class FakeDownloadGrantsAudit:
    rows: list[DownloadGrantRow] = field(default_factory=list)

    def get_by_request_id(self, request_id: str) -> list[DownloadGrantRow]:
        rid = request_id.strip()
        return [row for row in self.rows if row.request_id == rid]

    def insert(self, row: DownloadGrantRow) -> DownloadGrantRow:
        self.rows.append(row)
        return row

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
        for idx, row in enumerate(self.rows):
            if row.id != grant_id:
                continue
            updated = DownloadGrantRow(
                id=row.id,
                created_at_utc=row.created_at_utc,
                request_id=row.request_id,
                object_key=object_key,
                source_table=source_table,
                source_id=source_id,
                sha256=sha256,
                actor_ref=row.actor_ref,
                operation=row.operation,
                ttl_seconds=ttl_seconds,
                expires_at_utc=expires_at_utc,
                mint_result=MINT_ISSUED,
                reason_code=None,
            )
            self.rows[idx] = updated
            return updated
        raise KeyError(f"grant not found: {grant_id}")


def source_table_allowed(source_table: str | None) -> bool:
    table = (source_table or "").strip()
    if not table:
        return True
    return table in ALLOWED_SOURCE_TABLES


def object_key_prefix_ok(object_key: str) -> bool:
    key = object_key.strip()
    if not key or key.startswith("/") or ".." in key:
        return False
    return any(key.startswith(prefix) for prefix in KNOWN_OBJECT_PREFIXES)


def normalize_ttl(ttl_seconds: int) -> str | None:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
        return REASON_TTL_INVALID
    if ttl_seconds < TTL_MIN_SECONDS or ttl_seconds > TTL_MAX_SECONDS:
        return REASON_TTL_INVALID
    return None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _head_size_sha(head: object) -> tuple[int | None, str | None]:
    size = getattr(head, "size_bytes", None)
    sha = getattr(head, "byte_sha256", None)
    size_i = int(size) if size is not None else None
    sha_s = str(sha).strip().lower() if sha else None
    return size_i, sha_s


@dataclass
class SignedUrlMinter:
    """Fail-closed GetObject mint. Unit tests inject Fake ports."""

    entitlement: EntitlementProofPort
    resolver: CommittedObjectResolverPort
    audit: DownloadGrantsAuditPort
    r2: R2HeadAndPresignPort
    clock: Clock = utc_now

    def mint_get(self, request: MintRequest) -> MintOutcome:
        try:
            return self._mint_get(request)
        except FileNotFoundError:
            now = self.clock()
            return self._deny(
                request=request,
                now=now,
                reason=REASON_OBJECT_MISSING,
                object_key=(request.object_key or "").strip() or None,
            )
        except Exception as exc:
            name = type(exc).__name__
            if isinstance(exc, (OSError, TimeoutError, ConnectionError, RuntimeError)) or name in {
                "ClientError",
                "HTTPStatusError",
                "HTTPError",
                "ConnectError",
                "ReadTimeout",
                "WriteTimeout",
            }:
                rid = (request.request_id or "").strip() or None
                return MintOutcome(
                    exit_code=2,
                    mint_result=MINT_DENIED,
                    reason_code=None,
                    grant_id=None,
                    object_key=(request.object_key or "").strip() or None,
                    expires_at_utc=None,
                    signed_url=None,
                    request_id=rid,
                )
            raise

    def _mint_get(self, request: MintRequest) -> MintOutcome:
        now = self.clock()
        request_id = (request.request_id or "").strip()
        actor_ref = (request.actor_ref or "").strip()
        if not request_id or not actor_ref:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=(request.object_key or "").strip() or None,
            )

        operation = (request.operation or "").strip()
        if operation != OPERATION_GET_OBJECT:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_OPERATION_REJECTED,
                object_key=(request.object_key or "").strip() or None,
            )

        ttl_reason = normalize_ttl(request.ttl_seconds)
        if ttl_reason:
            return self._deny(
                request=request,
                now=now,
                reason=ttl_reason,
                object_key=(request.object_key or "").strip() or None,
            )

        object_key_in = (request.object_key or "").strip() or None
        source_table = (request.source_table or "").strip() or None
        source_id = (request.source_id or "").strip() or None
        if object_key_in is None and not (source_table and source_id):
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=None,
            )
        if (source_table and not source_id) or (source_id and not source_table):
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=object_key_in,
            )
        if not source_table_allowed(source_table):
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=object_key_in,
            )

        if object_key_in and source_table and source_id:
            ref = self.resolver.resolve(
                object_key=None,
                source_table=source_table,
                source_id=source_id,
            )
            if ref is None:
                return self._deny(
                    request=request,
                    now=now,
                    reason=REASON_NOT_COMMITTED,
                    object_key=object_key_in,
                )
            if ref.object_key != object_key_in:
                return self._deny(
                    request=request,
                    now=now,
                    reason=REASON_IDENTITY_MISMATCH,
                    object_key=object_key_in,
                    ref=ref,
                )
        else:
            ref = self.resolver.resolve(
                object_key=object_key_in,
                source_table=source_table,
                source_id=source_id,
            )
            if ref is None:
                return self._deny(
                    request=request,
                    now=now,
                    reason=REASON_ORPHAN if object_key_in else REASON_NOT_COMMITTED,
                    object_key=object_key_in,
                )

        if object_key_in and object_key_in != ref.object_key:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=object_key_in,
                ref=ref,
            )
        if source_table and (
            source_table != ref.source_table or (source_id and source_id != ref.source_id)
        ):
            return self._deny(
                request=request,
                now=now,
                reason=REASON_IDENTITY_MISMATCH,
                object_key=object_key_in or ref.object_key,
                ref=ref,
            )

        resolved_key = ref.object_key
        status = (ref.status or "").strip()
        if status == STATUS_ORPHAN:
            return self._deny(
                request=request, now=now, reason=REASON_ORPHAN, object_key=resolved_key, ref=ref
            )
        if status != STATUS_COMMITTED:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_NOT_COMMITTED,
                object_key=resolved_key,
                ref=ref,
            )

        if not object_key_prefix_ok(resolved_key):
            return self._deny(
                request=request,
                now=now,
                reason=REASON_PREFIX_REJECTED,
                object_key=resolved_key,
                ref=ref,
            )

        existing = self.audit.get_by_request_id(request_id)
        issued_existing = [row for row in existing if row.mint_result == MINT_ISSUED]
        conflicting = [row for row in issued_existing if row.object_key != resolved_key]
        if conflicting:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_REQUEST_ID_CONFLICT,
                object_key=resolved_key,
                ref=ref,
            )
        refresh_row = issued_existing[0] if issued_existing else None

        try:
            proof = self.entitlement.prove(actor_ref=actor_ref, object_key=resolved_key)
        except Exception:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_ENTITLEMENT_UNPROVEN,
                object_key=resolved_key,
                ref=ref,
            )
        if proof == PROOF_DENIED:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_ENTITLEMENT_DENIED,
                object_key=resolved_key,
                ref=ref,
            )
        if proof != PROOF_PROVEN:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_ENTITLEMENT_UNPROVEN,
                object_key=resolved_key,
                ref=ref,
            )

        if self.r2.delivery_bucket_is_public():
            return self._deny(
                request=request,
                now=now,
                reason=REASON_PUBLIC_BUCKET_FORBIDDEN,
                object_key=resolved_key,
                ref=ref,
            )

        try:
            head = self.r2.head_object(resolved_key)
        except FileNotFoundError:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_OBJECT_MISSING,
                object_key=resolved_key,
                ref=ref,
            )

        head_size, head_sha = _head_size_sha(head)
        if ref.size_bytes is not None and head_size is not None and int(ref.size_bytes) != head_size:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_CHECKSUM_MISMATCH,
                object_key=resolved_key,
                ref=ref,
            )
        if ref.sha256 and head_sha and str(ref.sha256).strip().lower() != head_sha:
            return self._deny(
                request=request,
                now=now,
                reason=REASON_CHECKSUM_MISMATCH,
                object_key=resolved_key,
                ref=ref,
            )

        expires = now + timedelta(seconds=request.ttl_seconds)
        expires_s = _iso(expires)
        signed_url = self.r2.presign_get_object(resolved_key, ttl_seconds=request.ttl_seconds)
        if not signed_url or " " in signed_url:
            raise RuntimeError("presign returned empty URL")
        host_ok = "r2.cloudflarestorage.com" in signed_url
        if not host_ok:
            raise RuntimeError("presign host is not R2 S3 API domain")

        sha_out = str(ref.sha256).strip() if ref.sha256 else head_sha
        if refresh_row is not None:
            stored = self.audit.update_issued(
                refresh_row.id,
                expires_at_utc=expires_s,
                ttl_seconds=request.ttl_seconds,
                sha256=sha_out,
                object_key=resolved_key,
                source_table=ref.source_table,
                source_id=ref.source_id,
            )
        else:
            stored = self.audit.insert(
                DownloadGrantRow(
                    id=str(uuid4()),
                    created_at_utc=_iso(now),
                    request_id=request_id,
                    object_key=resolved_key,
                    source_table=ref.source_table,
                    source_id=ref.source_id,
                    sha256=sha_out,
                    actor_ref=actor_ref,
                    operation=OPERATION_GET_OBJECT,
                    ttl_seconds=request.ttl_seconds,
                    expires_at_utc=expires_s,
                    mint_result=MINT_ISSUED,
                    reason_code=None,
                )
            )
        return MintOutcome(
            exit_code=0,
            mint_result=MINT_ISSUED,
            reason_code=None,
            grant_id=stored.id,
            object_key=resolved_key,
            expires_at_utc=expires_s,
            signed_url=signed_url,
            request_id=request_id,
        )

    def _deny(
        self,
        *,
        request: MintRequest,
        now: datetime,
        reason: str,
        object_key: str | None,
        ref: CommittedObjectRef | None = None,
    ) -> MintOutcome:
        if reason not in _REASON_CODES:
            reason = REASON_ENTITLEMENT_UNPROVEN
        request_id = (request.request_id or "").strip() or "invalid"
        actor_ref = (request.actor_ref or "").strip() or "invalid"
        ttl = request.ttl_seconds if isinstance(request.ttl_seconds, int) else TTL_DEFAULT_SECONDS
        row = self.audit.insert(
            DownloadGrantRow(
                id=str(uuid4()),
                created_at_utc=_iso(now),
                request_id=request_id,
                object_key=object_key or "",
                source_table=ref.source_table if ref else request.source_table,
                source_id=ref.source_id if ref else request.source_id,
                sha256=ref.sha256 if ref else None,
                actor_ref=actor_ref,
                operation=(request.operation or OPERATION_GET_OBJECT),
                ttl_seconds=ttl if isinstance(ttl, int) else TTL_DEFAULT_SECONDS,
                expires_at_utc=None,
                mint_result=MINT_DENIED,
                reason_code=reason,
            )
        )
        return MintOutcome(
            exit_code=1,
            mint_result=MINT_DENIED,
            reason_code=reason,
            grant_id=row.id,
            object_key=object_key,
            expires_at_utc=None,
            signed_url=None,
            request_id=request_id,
        )


