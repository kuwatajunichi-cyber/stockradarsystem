"""Language-independent mint golden cases: Python SignedUrlMinter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stockradar.storage.r2_object_store import FakeR2ObjectStore
from stockradar.storage.signed_url import (
    CommittedObjectRef,
    FakeCommittedObjectResolver,
    FakeDownloadGrantsAudit,
    FixedEntitlementProof,
    MintRequest,
    SignedUrlMinter,
)

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]
_GOLDEN = _REPO / "tests" / "fixtures" / "web_ui_bff" / "mint_golden.json"
_FIXED_NOW = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class _HeadOverrideR2:
    def __init__(self, inner: FakeR2ObjectStore, override: dict[str, object] | None) -> None:
        self.inner = inner
        self.override = override or {}

    def delivery_bucket_is_public(self) -> bool:
        return self.inner.delivery_bucket_is_public()

    def presign_get_object(self, object_key: str, *, ttl_seconds: int) -> str:
        return self.inner.presign_get_object(object_key, ttl_seconds=ttl_seconds)

    def head_object(self, object_key: str) -> object:
        head = self.inner.head_object(object_key)
        size = self.override.get("size_bytes", head.size_bytes)
        sha = self.override.get("byte_sha256", head.byte_sha256)
        return type(head)(
            object_key=head.object_key,
            size_bytes=int(size),
            byte_sha256=str(sha),
            content_type=head.content_type,
        )


def _ref(spec: dict, body: bytes) -> CommittedObjectRef:
    digest = _sha(body)
    return CommittedObjectRef(
        object_key=spec["object_key"],
        source_table=spec["source_table"],
        source_id=spec["source_id"],
        status=spec["status"],
        sha256=digest,
        size_bytes=len(body),
    )


def _run_one(case: dict, golden: dict) -> object:
    body = bytes.fromhex(golden["body_hex"])
    resolver = FakeCommittedObjectResolver()
    committed = _ref(golden["committed"], body)
    resolver.add(committed)
    extra = case.get("extra_object")
    if extra:
        resolver.add(_ref(extra, body))
    store = FakeR2ObjectStore()
    store.put_create_only(committed.object_key, body)
    if extra:
        store.put_create_only(extra["object_key"], body)
    r2 = _HeadOverrideR2(store, case.get("head_override"))
    audit = FakeDownloadGrantsAudit()
    minter = SignedUrlMinter(
        entitlement=FixedEntitlementProof(str(case.get("proof") or "unproven")),
        resolver=resolver,
        audit=audit,
        r2=r2,
        clock=lambda: _FIXED_NOW,
    )
    prior_grant = None
    if case.get("setup") == "issued":
        issued_case = next(c for c in golden["cases"] if c["id"] == "issued")
        minter.entitlement = FixedEntitlementProof("proven")
        seed = minter.mint_get(MintRequest(**issued_case["request"]))
        assert seed.exit_code == 0
        prior_grant = seed.grant_id
        minter.entitlement = FixedEntitlementProof(str(case.get("proof") or "proven"))
    out = minter.mint_get(MintRequest(**case["request"]))
    expect = case["expect"]
    assert out.exit_code == expect["exit_code"], case["id"]
    assert out.mint_result == expect["mint_result"], case["id"]
    assert out.reason_code == expect["reason_code"], case["id"]
    if out.mint_result == "issued":
        assert out.signed_url
        assert "r2.cloudflarestorage.com" in out.signed_url
        assert "signed_url" not in out.public_dict()
    else:
        assert out.signed_url is None
        assert any(r.reason_code == expect["reason_code"] for r in audit.rows)
    if expect.get("same_grant"):
        assert prior_grant
        assert out.grant_id == prior_grant
    return out


def test_mint_golden_python_matches_fixture() -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    for case in golden["cases"]:
        _run_one(case, golden)
