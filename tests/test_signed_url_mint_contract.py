"""Unit tests: Track B signed URL mint is fail-closed (Fake I/O only)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from stockradar.storage.r2_object_store import FakeR2ObjectStore
from stockradar.storage.signed_url import (
    OPERATION_GET_OBJECT,
    PROOF_DENIED,
    PROOF_PROVEN,
    PROOF_UNPROVEN,
    REASON_CHECKSUM_MISMATCH,
    REASON_ENTITLEMENT_DENIED,
    REASON_ENTITLEMENT_UNPROVEN,
    REASON_IDENTITY_MISMATCH,
    REASON_NOT_COMMITTED,
    REASON_OBJECT_MISSING,
    REASON_OPERATION_REJECTED,
    REASON_ORPHAN,
    REASON_PREFIX_REJECTED,
    REASON_PUBLIC_BUCKET_FORBIDDEN,
    REASON_REQUEST_ID_CONFLICT,
    REASON_TTL_INVALID,
    STATUS_COMMITTED,
    STATUS_ORPHAN,
    STATUS_PENDING,
    CommittedObjectRef,
    FakeCommittedObjectResolver,
    FakeDownloadGrantsAudit,
    FixedEntitlementProof,
    MintRequest,
    SignedUrlMinter,
)

pytestmark = pytest.mark.unit

_FIXED_NOW = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
_KEY = "published/demo/object.bin"
_BODY = b"committed-bytes"


def _committed(
    *,
    status: str = STATUS_COMMITTED,
    object_key: str = _KEY,
    sha256: str | None = None,
    size_bytes: int | None = None,
) -> CommittedObjectRef:
    r2 = FakeR2ObjectStore()
    r2.put_create_only(object_key, _BODY)
    head = r2.head_object(object_key)
    return CommittedObjectRef(
        object_key=object_key,
        source_table="artifact_index",
        source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        status=status,
        sha256=sha256 if sha256 is not None else head.byte_sha256,
        size_bytes=size_bytes if size_bytes is not None else head.size_bytes,
    )


def _minter(
    *,
    proof: str = PROOF_PROVEN,
    ref: CommittedObjectRef | None = None,
    put_bytes: bytes | None = _BODY,
    public_bucket: bool = False,
    r2: FakeR2ObjectStore | None = None,
) -> tuple[SignedUrlMinter, FakeDownloadGrantsAudit, FakeR2ObjectStore]:
    resolver = FakeCommittedObjectResolver()
    if ref is None:
        ref = _committed()
    resolver.add(ref)
    store = r2 or FakeR2ObjectStore(public_bucket=public_bucket)
    if put_bytes is not None and ref.object_key not in store.objects:
        store.put_create_only(ref.object_key, put_bytes)
    audit = FakeDownloadGrantsAudit()
    minter = SignedUrlMinter(
        entitlement=FixedEntitlementProof(proof),
        resolver=resolver,
        audit=audit,
        r2=store,
        clock=lambda: _FIXED_NOW,
    )
    return minter, audit, store


def _req(**kwargs: object) -> MintRequest:
    payload: dict[str, object] = {
        "request_id": "req-1",
        "actor_ref": "ops-cli",
        "operation": OPERATION_GET_OBJECT,
        "object_key": _KEY,
        "ttl_seconds": 300,
    }
    payload.update(kwargs)
    return MintRequest(**payload)  # type: ignore[arg-type]


def test_happy_path_issues_getobject_url_without_storing_url() -> None:
    minter, audit, _store = _minter()
    out = minter.mint_get(_req())
    assert out.exit_code == 0
    assert out.mint_result == "issued"
    assert out.reason_code is None
    assert out.signed_url
    assert "r2.cloudflarestorage.com" in out.signed_url
    assert "signed_url" not in out.public_dict()
    assert out.public_dict()["signed_url_present"] is True
    stored = audit.rows[0]
    assert stored.mint_result == "issued"
    assert stored.reason_code is None
    assert not hasattr(stored, "signed_url") or getattr(stored, "signed_url", None) is None
    assert "X-Amz-Signature" not in str(stored)


def test_default_entitlement_unproven_is_deny() -> None:
    minter, audit, _ = _minter(proof=PROOF_UNPROVEN)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_ENTITLEMENT_UNPROVEN
    assert out.signed_url is None
    assert audit.rows[0].mint_result == "denied"


def test_entitlement_denied() -> None:
    minter, _, _ = _minter(proof=PROOF_DENIED)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_ENTITLEMENT_DENIED


def test_entitlement_exception_is_fail_closed_not_allow_stub() -> None:
    class BoomProof:
        def prove(self, *, actor_ref: str, object_key: str) -> str:
            raise RuntimeError("proof backend down")

    resolver = FakeCommittedObjectResolver()
    resolver.add(_committed())
    r2 = FakeR2ObjectStore()
    r2.put_create_only(_KEY, _BODY)
    audit = FakeDownloadGrantsAudit()
    minter = SignedUrlMinter(
        entitlement=BoomProof(),  # type: ignore[arg-type]
        resolver=resolver,
        audit=audit,
        r2=r2,
        clock=lambda: _FIXED_NOW,
    )
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_ENTITLEMENT_UNPROVEN


def test_pending_is_not_committed() -> None:
    minter, _, _ = _minter(ref=_committed(status=STATUS_PENDING), put_bytes=_BODY)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_NOT_COMMITTED


def test_orphan_status_refused() -> None:
    minter, _, _ = _minter(ref=_committed(status=STATUS_ORPHAN), put_bytes=_BODY)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_ORPHAN


def test_missing_committed_row_is_orphan() -> None:
    minter, _, _ = _minter(ref=_committed())
    out = minter.mint_get(_req(object_key="published/missing.bin"))
    assert out.exit_code == 1
    assert out.reason_code == REASON_ORPHAN


def test_put_and_delete_operations_rejected() -> None:
    minter, _, _ = _minter()
    for op in ("PutObject", "DELETE", "put"):
        out = minter.mint_get(_req(operation=op))
        assert out.exit_code == 1
        assert out.reason_code == REASON_OPERATION_REJECTED


def test_ttl_out_of_range() -> None:
    minter, _, _ = _minter()
    assert minter.mint_get(_req(ttl_seconds=59)).reason_code == REASON_TTL_INVALID
    assert minter.mint_get(_req(ttl_seconds=3601)).reason_code == REASON_TTL_INVALID
    assert minter.mint_get(_req(ttl_seconds=60)).exit_code == 0
    assert minter.mint_get(_req(ttl_seconds=3600, request_id="req-ttl-max")).exit_code == 0


def test_prefix_rejected() -> None:
    ref = _committed(object_key="secret/not-allowed.bin")
    r2 = FakeR2ObjectStore()
    r2.put_create_only(ref.object_key, _BODY)
    minter, _, _ = _minter(ref=ref, r2=r2, put_bytes=None)
    out = minter.mint_get(_req(object_key=ref.object_key))
    assert out.exit_code == 1
    assert out.reason_code == REASON_PREFIX_REJECTED


def test_identity_mismatch_object_key_vs_source() -> None:
    ref = _committed()
    minter, _, _ = _minter(ref=ref)
    out = minter.mint_get(
        _req(
            object_key="published/other.bin",
            source_table=ref.source_table,
            source_id=ref.source_id,
        )
    )
    assert out.exit_code == 1
    assert out.reason_code == REASON_IDENTITY_MISMATCH


def test_object_missing_on_head() -> None:
    ref = _committed()
    minter, _, store = _minter(ref=ref, put_bytes=_BODY)
    store.delete_object(_KEY)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_OBJECT_MISSING


def test_checksum_mismatch() -> None:
    ref = _committed(sha256="0" * 64)
    minter, _, _ = _minter(ref=ref, put_bytes=_BODY)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_CHECKSUM_MISMATCH


def test_public_bucket_forbidden() -> None:
    minter, _, _ = _minter(public_bucket=True)
    out = minter.mint_get(_req())
    assert out.exit_code == 1
    assert out.reason_code == REASON_PUBLIC_BUCKET_FORBIDDEN


def test_request_id_conflict_different_object() -> None:
    minter, audit, store = _minter()
    first = minter.mint_get(_req())
    assert first.exit_code == 0
    other = "runs/daily/x/artifacts/demo.bin"
    store.put_create_only(other, _BODY)
    head = store.head_object(other)
    minter.resolver.add(
        CommittedObjectRef(
            object_key=other,
            source_table="artifact_index",
            source_id="bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee",
            status=STATUS_COMMITTED,
            sha256=head.byte_sha256,
            size_bytes=head.size_bytes,
        )
    )
    second = minter.mint_get(_req(object_key=other))
    assert second.exit_code == 1
    assert second.reason_code == REASON_REQUEST_ID_CONFLICT
    assert second.signed_url is None
    assert any(row.reason_code == REASON_REQUEST_ID_CONFLICT for row in audit.rows)


def test_request_id_same_object_refreshes_without_new_url_in_audit() -> None:
    minter, audit, _ = _minter()
    first = minter.mint_get(_req())
    second = minter.mint_get(_req())
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.grant_id == second.grant_id
    issued = [row for row in audit.rows if row.mint_result == "issued"]
    assert len(issued) == 1
    assert second.signed_url
    assert second.expires_at_utc == first.expires_at_utc


def test_named_client_error_is_exit_2() -> None:
    class ClientError(Exception):
        pass

    class BoomHead(FakeR2ObjectStore):
        def head_object(self, object_key: str):  # type: ignore[override]
            raise ClientError("boom")

    r2 = BoomHead()
    r2.put_create_only(_KEY, _BODY)
    minter, _, _ = _minter(r2=r2, put_bytes=None)
    out = minter.mint_get(_req())
    assert out.exit_code == 2
    assert out.signed_url is None


def test_presign_runtime_failure_is_exit_2() -> None:
    class BoomR2(FakeR2ObjectStore):
        def presign_get_object(self, object_key: str, *, ttl_seconds: int) -> str:
            raise RuntimeError("sign failed")

    r2 = BoomR2()
    r2.put_create_only(_KEY, _BODY)
    minter, _, _ = _minter(r2=r2, put_bytes=None)
    out = minter.mint_get(_req())
    assert out.exit_code == 2
    assert out.signed_url is None


def test_work_paid_prefixes_are_capability_not_roles() -> None:
    for key in ("0011_work/a.bin", "0012_paid/b.bin"):
        ref = _committed(object_key=key)
        r2 = FakeR2ObjectStore()
        r2.put_create_only(key, _BODY)
        minter, _, _ = _minter(ref=ref, r2=r2, put_bytes=None)
        out = minter.mint_get(_req(object_key=key, request_id=f"req-{key}"))
        assert out.exit_code == 0, out.reason_code


def test_module_has_no_public_http_server() -> None:
    text = Path(__file__).resolve().parents[1].joinpath(
        "src", "stockradar", "storage", "signed_url.py"
    ).read_text(encoding="utf-8")
    assert "Flask" not in text
    assert "FastAPI" not in text
    assert "aiohttp" not in text
    cli = Path(__file__).resolve().parents[1].joinpath(
        "scripts", "storage", "signed_url_mint_cli.py"
    ).read_text(encoding="utf-8")
    assert "public Worker" in cli or "No public" in cli


def test_unknown_source_table_is_identity_mismatch() -> None:
    minter, _, _ = _minter()
    out = minter.mint_get(
        _req(
            object_key=_KEY,
            source_table="pg_proc",
            source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )
    )
    assert out.exit_code == 1
    assert out.reason_code == REASON_IDENTITY_MISMATCH
    assert out.signed_url is None


def test_s3_delivery_bucket_unset_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from stockradar.storage.r2_object_store import S3R2ObjectStore

    store = S3R2ObjectStore(
        access_key_id="x",
        secret_access_key="y",
        bucket="b",
        base_prefix="",
        endpoint_url="https://example.r2.cloudflarestorage.com",
    )
    monkeypatch.delenv("R2_PUBLIC_BUCKET", raising=False)
    assert store.delivery_bucket_is_public() is True
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "false")
    assert store.delivery_bucket_is_public() is False
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "true")
    assert store.delivery_bucket_is_public() is True


def test_monthly_blob_resolves_non_core_slot() -> None:
    from stockradar.storage.signed_url_supabase import _monthly_blob

    row = {
        "object_keys": {
            "core": {
                "object_key": "monthly/tag/core.csv",
                "sha256": "a" * 64,
                "size_bytes": 10,
            },
            "ipo": {
                "object_key": "monthly/tag/ipo.csv",
                "sha256": "b" * 64,
                "size_bytes": 20,
            },
        }
    }
    key, sha, size = _monthly_blob(row, "monthly/tag/ipo.csv")
    assert key == "monthly/tag/ipo.csv"
    assert sha == "b" * 64
    assert size == 20
    core_key, _, _ = _monthly_blob(row, None)
    assert core_key == "monthly/tag/core.csv"
