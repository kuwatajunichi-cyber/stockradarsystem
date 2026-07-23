"""CAS contract for metric registry (Phase 4.5 Blocker 3)."""
from __future__ import annotations

import pytest

from stockradar.storage.metric_registry import ActiveMetricSetCasConflictError, FakeMetricRegistryStore

pytestmark = pytest.mark.unit


def test_cas_first_activation() -> None:
    store = FakeMetricRegistryStore()
    new_id = store.seed_set(lifecycle="shadow")
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=new_id,
        writer_workflow="test",
        source_github_run_id=1,
    )
    assert store.get_active_metric_set_id() == new_id


def test_cas_conflict_no_mutation() -> None:
    store = FakeMetricRegistryStore()
    a = store.seed_set()
    b = store.seed_set()
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=a,
        writer_workflow="test",
        source_github_run_id=1,
    )
    with pytest.raises(ActiveMetricSetCasConflictError):
        store.activate_metric_set_cas(
            expected_set_id=b,
            new_set_id=b,
            writer_workflow="test",
            source_github_run_id=2,
        )
    assert store.get_active_metric_set_id() == a


def test_cas_successful_switch() -> None:
    store = FakeMetricRegistryStore()
    a = store.seed_set()
    b = store.seed_set()
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=a,
        writer_workflow="test",
        source_github_run_id=1,
    )
    store.activate_metric_set_cas(
        expected_set_id=a,
        new_set_id=b,
        writer_workflow="test",
        source_github_run_id=2,
    )
    assert store.get_active_metric_set_id() == b
    assert store.metric_set_versions[a]["lifecycle_status"] == "retired"


def test_cas_idempotent_retry_keeps_active_set() -> None:
    store = FakeMetricRegistryStore()
    active_id = store.seed_set(lifecycle="shadow")
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=active_id,
        writer_workflow="test",
        source_github_run_id=1,
    )
    store.activate_metric_set_cas(
        expected_set_id=active_id,
        new_set_id=active_id,
        writer_workflow="test",
        source_github_run_id=2,
    )
    assert store.get_active_metric_set_id() == active_id
    assert store.metric_set_versions[active_id]["lifecycle_status"] == "active"


def test_cas_retires_all_active_sets() -> None:
    store = FakeMetricRegistryStore()
    stale_a = store.seed_set(lifecycle="active")
    stale_b = store.seed_set(lifecycle="active")
    new_id = store.seed_set(lifecycle="shadow")
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=new_id,
        writer_workflow="test",
        source_github_run_id=1,
    )
    assert store.get_active_metric_set_id() == new_id
    assert store.metric_set_versions[stale_a]["lifecycle_status"] == "retired"
    assert store.metric_set_versions[stale_b]["lifecycle_status"] == "retired"
    assert store.metric_set_versions[new_id]["lifecycle_status"] == "active"


def test_cas_rejects_draft_activation() -> None:
    store = FakeMetricRegistryStore()
    active_id = store.seed_set(lifecycle="shadow")
    store.activate_metric_set_cas(
        expected_set_id=None,
        new_set_id=active_id,
        writer_workflow="test",
        source_github_run_id=1,
    )
    draft_id = store.seed_set(lifecycle="draft")
    with pytest.raises(RuntimeError, match="not activatable"):
        store.activate_metric_set_cas(
            expected_set_id=active_id,
            new_set_id=draft_id,
            writer_workflow="test",
            source_github_run_id=2,
        )
    assert store.get_active_metric_set_id() == active_id
    assert store.metric_set_versions[active_id]["lifecycle_status"] == "active"
