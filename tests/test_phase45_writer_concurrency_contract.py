"""Contract: derived writer concurrency equivalence and fail-fast."""
from __future__ import annotations

import os
from typing import Any

import pytest

from stockradar.jobs.write_derived_generation import (
    DerivedGenerationRequest,
    SnapshotInput,
    resolve_r2_concurrency,
    run_derived_generation,
)
from stockradar.storage.derived_generation import (
    FakeMetricGenerationStore,
    ObjectCoordinateConflictError,
)
from stockradar.storage.r2_object_store import FakeR2ObjectStore, R2ObjectAlreadyExistsError

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
SHA = "c" * 64


def _snapshot(values: dict[str, dict[str, Any]]) -> SnapshotInput:
    return SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )


def _request(*, run_id: int, latest: bool = False) -> DerivedGenerationRequest:
    return DerivedGenerationRequest(
        stage="4.5c",
        mode="normal",
        trade_date="2026-01-15",
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=run_id,
        metric_set_version_id=SET_ID,
        active_metric_set_id=SET_ID,
        lifecycle_status="active",
        is_active=True,
        is_current_latest_trade_date=latest,
    )


def _run(concurrency: int, *, run_id: int, values: dict[str, dict[str, Any]], latest: bool = False):
    os.environ["DERIVED_R2_CONCURRENCY"] = str(concurrency)
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    latest_rows = None
    if latest:
        # logical digest filled by writer path via snapshot digest; supply placeholder rows
        from stockradar.storage.derived_snapshot import (
            build_snapshot_rows,
            compute_snapshot_logical_digest,
        )

        rows = build_snapshot_rows(
            trade_date="2026-01-15",
            metric_set_version_id=SET_ID,
            metric_keys_ordered=["alpha_metric"],
            metric_types={"alpha_metric": "float"},
            values_by_instrument=values,
        )
        digest, _ = compute_snapshot_logical_digest(
            trade_date="2026-01-15",
            metric_set_version_id=SET_ID,
            rows=rows,
        )
        latest_rows = [
            {
                "instrument_code": code,
                "trade_date": "2026-01-15",
                "values_json": values[code],
                "logical_digest": digest,
            }
            for code in sorted(values)
        ]
    result = run_derived_generation(
        _request(run_id=run_id, latest=latest),
        snapshot_input=_snapshot(values),
        generation_store=generation_store,
        r2_store=r2_store,
        latest_rows=latest_rows,
    )
    return result, generation_store, r2_store


def test_resolve_r2_concurrency_defaults_and_floor() -> None:
    assert resolve_r2_concurrency("32") == 32
    assert resolve_r2_concurrency("0") == 1
    assert resolve_r2_concurrency("nope") == 32


def test_writer_concurrency_1_vs_8_same_digest_and_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {f"{1000 + i}": {"alpha_metric": float(i)} for i in range(12)}
    monkeypatch.delenv("DERIVED_R2_CONCURRENCY", raising=False)
    r1, store1, r2a = _run(1, run_id=101, values=values, latest=True)
    r8, store8, r2b = _run(8, run_id=102, values=values, latest=True)
    assert r1.exit_code == 0 and r8.exit_code == 0
    assert r1.logical_digest == r8.logical_digest
    assert r1.series_count == r8.series_count == 12
    assert r1.r2_concurrency == 1
    assert r8.r2_concurrency == 8
    # Manifest embeds generation_id; compare snapshot/series bodies only.
    series_a = sorted(v for k, v in r2a.objects.items() if "series-sha256=" in k)
    series_b = sorted(v for k, v in r2b.objects.items() if "series-sha256=" in k)
    assert series_a == series_b
    snap_a = sorted(v for k, v in r2a.objects.items() if "indicators-sha256=" in k)
    snap_b = sorted(v for k, v in r2b.objects.items() if "indicators-sha256=" in k)
    assert snap_a == snap_b
    assert set(store1.committed_series_object_key_by_coord.keys()) == set(
        store8.committed_series_object_key_by_coord.keys()
    )


def test_batch_register_digest_conflict_semantics() -> None:
    store = FakeMetricGenerationStore()
    from stockradar.storage.derived_generation import (
        ArtifactProfile,
        BeginGenerationRequest,
        SourceRunIdentity,
    )

    gen = store.begin_generation(
        BeginGenerationRequest(
            source=SourceRunIdentity(
                repository="org/repo",
                workflow="daily.yml",
                github_run_id=1,
                metric_set_version_id=SET_ID,
                trade_date="2026-01-15",
                mode="normal",
            ),
            artifact_profile=ArtifactProfile.SNAPSHOT_SERIES,
            new_logical_digest=SHA,
        )
    )
    payload = {
        "object_kind": "series",
        "object_key": "k1",
        "logical_digest": SHA,
        "byte_sha256": SHA,
        "size_bytes": 10,
        "instrument_code": "1301",
        "series_year": 2026,
    }
    store.register_pending_objects(generation_id=gen.generation_id, objects=[payload])
    conflict = dict(payload)
    conflict["logical_digest"] = "d" * 64
    with pytest.raises(ObjectCoordinateConflictError):
        store.register_pending_objects(generation_id=gen.generation_id, objects=[conflict])
    # same digest reuses
    again = store.register_pending_objects(generation_id=gen.generation_id, objects=[payload])
    assert len(again) == 1


def test_parallel_put_failure_marks_generation_failed_no_partial_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {"1301": {"alpha_metric": 1.0}, "1302": {"alpha_metric": 2.0}}
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()

    real_put = r2_store.put_create_only
    calls = {"n": 0}

    def flaky_put(object_key: str, content: bytes, *, content_type: str = "application/octet-stream"):
        calls["n"] += 1
        # Fail on a series object (not snapshot/manifest)
        if "symbol=" in object_key or "/series/" in object_key or "series" in object_key:
            if calls["n"] >= 3:
                raise TimeoutError("simulated r2 timeout")
        return real_put(object_key, content, content_type=content_type)

    monkeypatch.setattr(r2_store, "put_create_only", flaky_put)
    monkeypatch.setenv("DERIVED_R2_CONCURRENCY", "4")
    result = run_derived_generation(
        _request(run_id=201, latest=False),
        snapshot_input=_snapshot(values),
        generation_store=generation_store,
        r2_store=r2_store,
        latest_rows=None,
    )
    assert result.exit_code == 2
    assert result.status == "error"
    gens = [g for g in generation_store.generations.values()]
    assert gens
    assert any(g.get("status") == "failed" for g in gens)
    assert generation_store.committed_series_object_key_by_coord == {}
