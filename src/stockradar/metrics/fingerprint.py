"""Deterministic fingerprints for metric definitions and sets."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def compute_definition_fingerprint(definition_canonical: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(definition_canonical)).hexdigest()


def compute_set_fingerprint(*, members: list[dict[str, Any]], set_family: str) -> str:
    payload = {
        "set_family": set_family,
        "members": members,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def short_fingerprint12(full_fingerprint: str) -> str:
    if len(full_fingerprint) < 12:
        raise ValueError("fingerprint too short")
    return full_fingerprint[:12]
