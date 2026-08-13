"""Contract: Phase 4.5 derived generation Fake store + create-only R2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stockradar.storage.derived_generation import (
    ArtifactProfile,
    BeginGenerationRequest,
    FakeMetricGenerationStore,
    GenerationConflictError,
    GenerationStatus,
    SourceRunIdentity,
    profile_allows_latest,
    profile_allows_series,
    resolve_artifact_profile,
)
from stockradar.storage.r2_object_store import FakeR2ObjectStore, R2ObjectAlreadyExistsError

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
TRADE_DATE = "2026-01-15"
RUN_ID = 4242
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
SHA = "c" * 64


def _source(*, mode: str = "normal") -> SourceRunIdentity:
    return SourceRunIdentity(
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=RUN_ID,
        metric_set_version_id=SET_ID,
        trade_date=TRADE_DATE,
        mode=mode,
    )


def _begin(
    store: FakeMetricGenerationStore,
    profile: ArtifactProfile,
    *,
    mode: str = "normal",
) -> str:
    record = store.begin_generation(
        BeginGenerationRequest(
            source=_source(mode=mode),
            artifact_profile=profile,
            new_logical_digest=DIGEST_A,
        )
    )
    return record.generation_id


def _register_snapshot(store: FakeMetricGenerationStore, generation_id: str) -> None:
    store.register_pending_object(
        generation_id=generation_id,
        object_kind="snapshot",
        object_key=f"derived-snapshots/metric-set={SET_ID}/trade-date={TRADE_DATE}/generation={generation_id}/indicators-sha256={SHA}.parquet",
        logical_digest=DIGEST_A,
        byte_sha256=SHA,
        size_bytes=128,
        trade_date=TRADE_DATE,
    )
    store.mark_object_uploaded(
        generation_id=generation_id,
        object_key=f"derived-snapshots/metric-set={SET_ID}/trade-date={TRADE_DATE}/generation={generation_id}/indicators-sha256={SHA}.parquet",
        byte_sha256=SHA,
        size_bytes=128,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "stage,mode,is_latest,expected",
    [
        ("4.5a", "normal", False, ArtifactProfile.SNAPSHOT_ONLY),
        ("4.5b", "normal", False, ArtifactProfile.SNAPSHOT_SERIES),
        ("4.5c", "normal", False, ArtifactProfile.SNAPSHOT_SERIES_LATEST),
        ("4.5c", "reconcile", True, ArtifactProfile.SNAPSHOT_SERIES_LATEST),
        ("4.5c", "reconcile", False, ArtifactProfile.SNAPSHOT_SERIES),
    ],
)
def test_resolve_artifact_profile_three_profiles(
    stage: str,
    mode: str,
    is_latest: bool,
    expected: ArtifactProfile,
) -> None:
    profile = resolve_artifact_profile(
        stage=stage,
        mode=mode,
        is_current_latest_trade_date=is_latest,
    )
    assert profile == expected
    assert profile_allows_series(profile) == (expected != ArtifactProfile.SNAPSHOT_ONLY)
    assert profile_allows_latest(profile) == (expected == ArtifactProfile.SNAPSHOT_SERIES_LATEST)


@pytest.mark.unit
def test_begin_generation_retry_is_noop_for_pending() -> None:
    store = FakeMetricGenerationStore()
    first = store.begin_generation(
        BeginGenerationRequest(
            source=_source(),
            artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
            new_logical_digest=DIGEST_A,
        )
    )
    second = store.begin_generation(
        BeginGenerationRequest(
            source=_source(),
            artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
            new_logical_digest=DIGEST_A,
        )
    )
    assert first.generation_id == second.generation_id
    assert second.status == GenerationStatus.PENDING.value


@pytest.mark.unit
def test_begin_generation_committed_same_digest_is_idempotent() -> None:
    store = FakeMetricGenerationStore()
    generation_id = _begin(store, ArtifactProfile.SNAPSHOT_ONLY)
    _register_snapshot(store, generation_id)
    store.commit_generation(generation_id=generation_id, new_logical_digest=DIGEST_A)
    replay = store.begin_generation(
        BeginGenerationRequest(
            source=_source(),
            artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
            new_logical_digest=DIGEST_A,
        )
    )
    assert replay.generation_id == generation_id
    assert replay.status == GenerationStatus.COMMITTED.value


@pytest.mark.unit
def test_begin_generation_committed_different_digest_conflicts() -> None:
    store = FakeMetricGenerationStore()
    generation_id = _begin(store, ArtifactProfile.SNAPSHOT_ONLY)
    _register_snapshot(store, generation_id)
    store.commit_generation(generation_id=generation_id, new_logical_digest=DIGEST_A)
    with pytest.raises(GenerationConflictError):
        store.begin_generation(
            BeginGenerationRequest(
                source=_source(),
                artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
                new_logical_digest=DIGEST_B,
            )
        )


@pytest.mark.unit
def test_list_stale_generations_filters_by_heartbeat() -> None:
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    store = FakeMetricGenerationStore(_clock=now - timedelta(hours=2))
    generation_id = _begin(store, ArtifactProfile.SNAPSHOT_ONLY)
    store.heartbeat(generation_id=generation_id)
    stale = store.list_stale_generations(stale_after=timedelta(hours=1), now_utc=now)
    assert len(stale) == 1
    assert stale[0].generation_id == generation_id


@pytest.mark.unit
def test_fake_r2_put_create_only_and_noop() -> None:
    store = FakeR2ObjectStore()
    payload = b"phase45-test-payload"
    created = store.put_create_only("derived/test/object.json", payload, content_type="application/json")
    assert created.noop is False
    assert store.get_object("derived/test/object.json") == payload

    same = store.put_create_only("derived/test/object.json", payload, content_type="application/json")
    assert same.noop is True

    with pytest.raises(R2ObjectAlreadyExistsError):
        store.put_create_only("derived/test/object.json", b"different-bytes")


@pytest.mark.unit
def test_run_derived_generation_registers_single_snapshot_index_row() -> None:
    from stockradar.jobs.write_derived_generation import (
        DerivedGenerationRequest,
        SnapshotInput,
        run_derived_generation,
    )

    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    values = {"1301": {"alpha_metric": 1.0}}
    snapshot_input = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage="4.5a",
        mode="normal",
        trade_date=TRADE_DATE,
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=RUN_ID,
        metric_set_version_id=SET_ID,
        active_metric_set_id=None,
        lifecycle_status="shadow",
        is_active=False,
        is_current_latest_trade_date=False,
    )
    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    assert result.exit_code == 0
    assert result.generation_id is not None
    pending = generation_store.list_pending_objects(result.generation_id)
    snapshot_rows = [row for row in pending if row.object_kind == "snapshot"]
    assert len(snapshot_rows) == 1
    assert snapshot_rows[0].object_key.endswith(".parquet")
    assert any(key.endswith(".json") for key in result.object_keys)


@pytest.mark.unit
def test_run_derived_generation_stages_latest_rows() -> None:
    from stockradar.jobs.write_derived_generation import (
        DerivedGenerationRequest,
        SnapshotInput,
        run_derived_generation,
    )

    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    values = {"1301": {"alpha_metric": 1.0}}
    snapshot_input = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage="4.5c",
        mode="normal",
        trade_date=TRADE_DATE,
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=RUN_ID,
        metric_set_version_id=SET_ID,
        active_metric_set_id=SET_ID,
        lifecycle_status="active",
        is_active=True,
        is_current_latest_trade_date=True,
    )
    latest_rows = [
        {
            "instrument_code": "1301",
            "trade_date": TRADE_DATE,
            "values_json": values["1301"],
            "logical_digest": DIGEST_A,
        }
    ]
    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store,
        r2_store=r2_store,
        latest_rows=latest_rows,
    )
    assert result.exit_code == 0
    committed = generation_store.committed_latest_observations[(SET_ID, "1301")]
    assert committed["trade_date"] == TRADE_DATE
    assert committed["logical_digest"] == DIGEST_A


@pytest.mark.unit
def test_run_derived_generation_committed_replay_is_noop() -> None:
    from stockradar.jobs.write_derived_generation import (
        DerivedGenerationRequest,
        SnapshotInput,
        run_derived_generation,
    )

    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    values = {"1301": {"alpha_metric": 1.0}}
    snapshot_input = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage="4.5a",
        mode="normal",
        trade_date=TRADE_DATE,
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=RUN_ID,
        metric_set_version_id=SET_ID,
        active_metric_set_id=None,
        lifecycle_status="shadow",
        is_active=False,
        is_current_latest_trade_date=False,
    )
    first = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    second = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert second.skipped
    assert second.reason == "generation_already_committed"


@pytest.mark.unit
def test_run_derived_generation_4_5b_includes_series_object() -> None:
    from stockradar.jobs.write_derived_generation import (
        DerivedGenerationRequest,
        SnapshotInput,
        run_derived_generation,
    )

    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    values = {"1301": {"alpha_metric": 1.0}}
    snapshot_input = SnapshotInput(
        metric_keys_ordered=["alpha_metric"],
        metric_types={"alpha_metric": "float"},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage="4.5b",
        mode="normal",
        trade_date=TRADE_DATE,
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=RUN_ID + 1,
        metric_set_version_id=SET_ID,
        active_metric_set_id=None,
        lifecycle_status="shadow",
        is_active=False,
        is_current_latest_trade_date=False,
    )
    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=generation_store,
        r2_store=r2_store,
    )
    assert result.exit_code == 0
    pending = generation_store.list_pending_objects(result.generation_id)
    kinds = {row.object_kind for row in pending}
    assert kinds == {"snapshot", "series"}
