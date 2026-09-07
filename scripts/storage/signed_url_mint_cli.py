"""Internal CLI: mint GetObject signed URL (Track B). No public endpoint."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.r2_object_store import (  # noqa: E402
    FakeR2ObjectStore,
    S3R2ObjectStore,
)
from stockradar.storage.signed_url import (  # noqa: E402
    OPERATION_GET_OBJECT,
    PROOF_DENIED,
    PROOF_PROVEN,
    PROOF_UNPROVEN,
    STATUS_COMMITTED,
    CommittedObjectRef,
    FakeCommittedObjectResolver,
    FakeDownloadGrantsAudit,
    FixedEntitlementProof,
    MintRequest,
    SignedUrlMinter,
)

ENV_FAKE = "SIGNED_URL_FAKE"
ENV_ALLOW_FIXTURE = "SIGNED_URL_MINT_ALLOW_FIXTURE"
_PROOF_VALUES = {PROOF_PROVEN, PROOF_UNPROVEN, PROOF_DENIED}


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _emit_public(payload: dict[str, object], json_output: str | None, caller: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output:
        Path(json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(json_output).write_text(json.dumps(caller, ensure_ascii=False) + "\n", encoding="utf-8")


def _entitlement_port(fixture: str | None) -> FixedEntitlementProof:
    if not fixture:
        return FixedEntitlementProof(PROOF_UNPROVEN)
    value = fixture.strip()
    if value not in _PROOF_VALUES:
        return FixedEntitlementProof(PROOF_UNPROVEN)
    if not _truthy(ENV_ALLOW_FIXTURE):
        return FixedEntitlementProof(PROOF_UNPROVEN)
    return FixedEntitlementProof(value)


def _load_committed_fixture(path: str) -> tuple[FakeCommittedObjectResolver, FakeR2ObjectStore]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("fixture must be a JSON object")
    object_key = str(raw.get("object_key") or "").strip()
    body = str(raw.get("body") or "fixture-bytes").encode("utf-8")
    sha256 = str(raw.get("sha256") or "").strip() or None
    size_bytes = raw.get("size_bytes")
    r2 = FakeR2ObjectStore()
    r2.put_create_only(object_key, body, content_type="application/octet-stream")
    head = r2.head_object(object_key)
    resolver = FakeCommittedObjectResolver()
    resolver.add(
        CommittedObjectRef(
            object_key=object_key,
            source_table=str(raw.get("source_table") or "artifact_index"),
            source_id=str(raw.get("source_id") or uuid4()),
            status=STATUS_COMMITTED,
            sha256=sha256 or head.byte_sha256,
            size_bytes=int(size_bytes) if size_bytes is not None else head.size_bytes,
        )
    )
    return resolver, r2


def _build_minter(args: argparse.Namespace) -> SignedUrlMinter:
    entitlement = _entitlement_port(getattr(args, "entitlement_fixture", None))
    if _truthy(ENV_FAKE) or os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        fixture_path = getattr(args, "fixture_committed_json", None)
        if not fixture_path:
            resolver = FakeCommittedObjectResolver()
            r2: FakeR2ObjectStore | S3R2ObjectStore = FakeR2ObjectStore()
        else:
            resolver, r2 = _load_committed_fixture(str(fixture_path))
        return SignedUrlMinter(
            entitlement=entitlement,
            resolver=resolver,
            audit=FakeDownloadGrantsAudit(),
            r2=r2,
        )
    from stockradar.storage.signed_url_supabase import (  # noqa: E402
        RestCommittedObjectResolver,
        RestDownloadGrantsAudit,
    )

    return SignedUrlMinter(
        entitlement=entitlement,
        resolver=RestCommittedObjectResolver.from_env(),
        audit=RestDownloadGrantsAudit.from_env(),
        r2=S3R2ObjectStore.from_env(),
    )


def cmd_mint(args: argparse.Namespace) -> int:
    try:
        minter = _build_minter(args)
    except RuntimeError as exc:
        payload = {
            "exit_code": 2,
            "mint_result": "denied",
            "reason_code": None,
            "error": str(exc),
            "signed_url_present": False,
        }
        _emit_public(payload, args.json_output, payload)
        return 2

    ttl = int(args.ttl_seconds)
    outcome = minter.mint_get(
        MintRequest(
            request_id=args.request_id,
            actor_ref=args.actor_ref,
            operation=args.operation,
            object_key=args.object_key or None,
            source_table=args.source_table or None,
            source_id=args.source_id or None,
            ttl_seconds=ttl,
        )
    )
    public = outcome.public_dict()
    _emit_public(public, args.json_output, outcome.caller_dict())
    return int(outcome.exit_code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track B internal GetObject signed URL mint. No public Worker."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_mint = sub.add_parser("mint")
    p_mint.add_argument("--request-id", required=True)
    p_mint.add_argument("--actor-ref", required=True)
    p_mint.add_argument("--object-key", default="")
    p_mint.add_argument("--source-table", default="")
    p_mint.add_argument("--source-id", default="")
    p_mint.add_argument("--operation", default=OPERATION_GET_OBJECT)
    p_mint.add_argument("--ttl-seconds", type=int, default=300)
    p_mint.add_argument(
        "--entitlement-fixture",
        default=None,
        help="proven|unproven|denied. Honored only when SIGNED_URL_MINT_ALLOW_FIXTURE=1",
    )
    p_mint.add_argument(
        "--fixture-committed-json",
        default=None,
        help="Fake-mode committed object seed (SIGNED_URL_FAKE=1 only)",
    )
    p_mint.add_argument("--json-output", required=True)
    p_mint.set_defaults(func=cmd_mint)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.exit(int(args.func(args)))


if __name__ == "__main__":
    main()
