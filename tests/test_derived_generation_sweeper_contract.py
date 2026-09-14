"""Contract tests for ADR-005 derived_generation_sweeper."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.storage.derived_generation_sweeper import (
    GENERATION_SWEEP_PREFIX_ROOTS,
    KIND_BLOCKED_LATEST,
    KIND_MIXED,
    KIND_ORPHAN_ONLY,
    classify_generation_for_prefix_delete,
    generation_sweep_prefixes,
    plan_generation_sweeps,
    should_delete_orphan_object_key,
    should_prefix_delete_generation,
)

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]


def test_sweeper_file_excludes_derived_inputs() -> None:
    body = (_REPO / "scripts" / "storage" / "derived_generation_sweeper.py").read_text(
        encoding="utf-8"
    )
    assert "derived-snapshots/" in body
    assert "derived-series/" in body
    assert "not delete derived-inputs" in body.lower()
    assert GENERATION_SWEEP_PREFIX_ROOTS == ("derived-snapshots/", "derived-series/")


def test_prefix_helper_roots() -> None:
    prefixes = generation_sweep_prefixes(
        generation_id="g1",
        metric_set_version_id="s1",
        trade_date="2026-08-01",
    )
    assert all(
        p.startswith("derived-snapshots/") or p.startswith("derived-series/") for p in prefixes
    )
    assert not any("derived-inputs/" in p for p in prefixes)


def test_prefix_delete_only_orphan_only_generations() -> None:
    assert (
        classify_generation_for_prefix_delete(statuses={"orphan"}, latest_row_count=0)
        == KIND_ORPHAN_ONLY
    )
    assert should_prefix_delete_generation(KIND_ORPHAN_ONLY) is True
    mixed = classify_generation_for_prefix_delete(
        statuses={"orphan", "committed"},
        latest_row_count=0,
    )
    assert mixed == KIND_MIXED
    assert should_prefix_delete_generation(mixed) is False
    superseded = classify_generation_for_prefix_delete(
        statuses={"orphan", "superseded"},
        latest_row_count=0,
    )
    assert superseded == KIND_MIXED
    blocked = classify_generation_for_prefix_delete(
        statuses={"orphan"},
        latest_row_count=1,
    )
    assert blocked == KIND_BLOCKED_LATEST
    assert should_prefix_delete_generation(blocked) is False
    plans = plan_generation_sweeps(
        statuses_by_generation={
            "orphan-only": {"orphan"},
            "mixed": {"orphan", "pending"},
        },
        latest_counts={"orphan-only": 0, "mixed": 0},
    )
    by_id = {item.generation_id: item for item in plans}
    assert by_id["orphan-only"].prefix_delete is True
    assert by_id["mixed"].prefix_delete is False


def test_sweeper_refuses_mixed_prefix_in_source() -> None:
    body = (_REPO / "scripts" / "storage" / "derived_generation_sweeper.py").read_text(
        encoding="utf-8"
    )
    assert "Prefix-delete only orphan-only generations" in body
    assert "should_prefix_delete_generation" in body
    assert "--delete-orphan-rows" in body


def test_protect_committed_and_inputs() -> None:
    assert (
        should_delete_orphan_object_key(
            object_key="derived-inputs/x",
            object_kind="series_seed_delta",
            committed_object_keys=set(),
        )
        is False
    )
    assert (
        should_delete_orphan_object_key(
            object_key="derived-series/x",
            object_kind="series",
            committed_object_keys={"derived-series/x"},
        )
        is False
    )
    assert (
        should_delete_orphan_object_key(
            object_key="derived-series/y",
            object_kind="series",
            committed_object_keys=set(),
        )
        is True
    )
