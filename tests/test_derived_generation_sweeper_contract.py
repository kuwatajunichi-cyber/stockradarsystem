"""Contract tests for ADR-005 derived_generation_sweeper."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.storage.derived_generation_sweeper import (
    GENERATION_SWEEP_PREFIX_ROOTS,
    generation_sweep_prefixes,
    should_delete_orphan_object_key,
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
