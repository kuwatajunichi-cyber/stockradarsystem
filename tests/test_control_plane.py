"""Unit tests for control_plane pure helpers."""
from __future__ import annotations

import pytest

from stockradar.storage.control_plane import (
    build_patched_object_keys,
    filter_patched_keys_by_allowed_refs,
    normalize_rollout_stage,
    resolve_patched_r2_keys,
    supabase_commit_is_fatal,
)

pytestmark = pytest.mark.unit


def test_normalize_rollout_stage() -> None:
    assert normalize_rollout_stage("3c") == "3c"
    with pytest.raises(ValueError):
        normalize_rollout_stage("4")


def test_supabase_commit_is_fatal_only_3c() -> None:
    assert supabase_commit_is_fatal("3a") is False
    assert supabase_commit_is_fatal("3b") is False
    assert supabase_commit_is_fatal("3c") is True


def test_filter_patched_keys_by_allowed_refs() -> None:
    rows = [
        {"cache_key": "universe-patched-m-2026-04-01", "source_ref": "refs/heads/main"},
        {"cache_key": "universe-patched-m-2026-04-02", "source_ref": "refs/heads/other"},
    ]
    allowed = frozenset({"refs/heads/main"})
    assert filter_patched_keys_by_allowed_refs(rows, allowed) == [
        "universe-patched-m-2026-04-01"
    ]


def test_build_patched_object_keys_shape() -> None:
    csv_k, man_k = resolve_patched_r2_keys(monthly_tag="monthly-1", run_date="2026-04-10")
    doc = build_patched_object_keys(
        csv_object_key=csv_k,
        csv_sha256="a" * 64,
        csv_size_bytes=10,
        manifest_object_key=man_k,
        manifest_sha256="b" * 64,
        manifest_size_bytes=20,
    )
    assert doc["cache_index_schema_version"] == 1
    assert doc["csv"]["object_key"] == csv_k
    assert doc["manifest"]["content_type"] == "application/json"
