"""Contract: Phase 4.5 production adapter factories and Supabase RPC mapping."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from stockradar.storage.derived_adapters import (
    generation_store_from_env,
    is_derived_generation_fake,
    registry_store_from_env,
    r2_store_from_env,
)
from stockradar.storage.derived_generation import (
    ArtifactProfile,
    BeginGenerationRequest,
    FakeMetricGenerationStore,
    SourceRunIdentity,
)
from stockradar.storage.metric_registry import FakeMetricRegistryStore
from stockradar.storage.r2_object_store import FakeR2ObjectStore, S3R2ObjectStore
from stockradar.storage.supabase_metric_generation import SupabaseMetricGenerationAdapter
from stockradar.storage.supabase_metric_registry import SupabaseMetricRegistryAdapter

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
GEN_ID = "22222222-3333-4444-5555-666666666666"
DIGEST = "a" * 64


def test_factory_selects_fake_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    assert is_derived_generation_fake()
    assert isinstance(generation_store_from_env(), FakeMetricGenerationStore)
    assert isinstance(r2_store_from_env(), FakeR2ObjectStore)
    assert isinstance(registry_store_from_env(), FakeMetricRegistryStore)


def test_factory_requires_supabase_when_not_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DERIVED_GENERATION_FAKE", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        generation_store_from_env()


def test_supabase_generation_begin_calls_rpc() -> None:
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
        writer_workflow="daily.yml",
    )
    generation_row = {
        "id": GEN_ID,
        "metric_set_version_id": SET_ID,
        "trade_date": "2026-01-15",
        "mode": "normal",
        "artifact_profile": ArtifactProfile.SNAPSHOT_ONLY.value,
        "repository": "org/repo",
        "workflow": "daily.yml",
        "github_run_id": 99,
        "status": "pending",
        "expected_old_digest": None,
        "declared_new_digest": DIGEST,
        "new_digest": None,
        "heartbeat_at": "2026-01-15T00:00:00+00:00",
        "created_at_utc": "2026-01-15T00:00:00+00:00",
        "committed_at_utc": None,
    }

    def fake_request(method, path, json_body=None, params=None, prefer=None, timeout_s=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        if path.endswith("/rpc/begin_derived_generation"):
            return httpx.Response(200, json=GEN_ID, request=request)
        if path.endswith("/derived_generation_runs"):
            return httpx.Response(200, json=[generation_row], request=request)
        raise AssertionError(f"unexpected request: {method} {path}")

    with patch.object(adapter, "_request", fake_request):
        record = adapter.begin_generation(
            BeginGenerationRequest(
                source=SourceRunIdentity(
                    repository="org/repo",
                    workflow="daily.yml",
                    github_run_id=99,
                    metric_set_version_id=SET_ID,
                    trade_date="2026-01-15",
                    mode="normal",
                ),
                artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
                new_logical_digest=DIGEST,
            )
        )
    assert record.generation_id == GEN_ID
    assert record.status == "pending"


def test_s3_r2_object_store_from_env_requires_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DERIVED_GENERATION_FAKE", raising=False)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.delenv("R2_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="R2_BUCKET"):
        S3R2ObjectStore.from_env()


def test_supabase_registry_get_active() -> None:
    adapter = SupabaseMetricRegistryAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
    )

    def fake_request(method, path, json_body=None, params=None, prefer=None, timeout_s=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        assert path.endswith("/active_metric_set")
        return httpx.Response(200, json=[{"metric_set_version_id": SET_ID}], request=request)

    with patch.object(adapter, "_request", fake_request):
        assert adapter.get_active_metric_set_id() == SET_ID


def test_mark_object_uploaded_uses_single_row_fetch_after_rpc() -> None:
    """Regression: PostgREST defaults to 1000 rows; mark must not rely on full pending list."""
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
        writer_workflow="daily.yml",
    )
    object_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    object_key = "derived-series/metric-set=test/symbol=5192/year=2026/gen.json.gz"
    adapter._object_ids_by_key[(GEN_ID, object_key)] = object_id
    row = {
        "id": object_id,
        "object_kind": "series",
        "object_key": object_key,
        "logical_digest": DIGEST,
        "byte_sha256": DIGEST,
        "size_bytes": 42,
        "upload_verified_at": "2026-08-14T09:00:00+00:00",
    }

    def fake_request(method, path, json_body=None, params=None, prefer=None, timeout_s=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        if path.endswith("/derived_object_index") and params and params.get("id"):
            return httpx.Response(200, json=[row], request=request)
        raise AssertionError(f"unexpected request: {method} {path} {params}")

    with patch.object(adapter, "_request", fake_request):
        with patch.object(adapter, "_rpc", lambda name, body: None):
            with patch.object(adapter, "list_pending_objects", lambda gid: []):
                record = adapter.mark_object_uploaded(
                    generation_id=GEN_ID,
                    object_key=object_key,
                    byte_sha256=DIGEST,
                    size_bytes=42,
                )
    assert record.object_id == object_id
    assert record.byte_sha256 == DIGEST


def test_supabase_batch_register_chunks_and_maps_by_object_key() -> None:
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
        writer_workflow="daily.yml",
    )
    objects = [
        {
            "object_kind": "series",
            "object_key": f"k-{i}",
            "logical_digest": DIGEST,
            "byte_sha256": DIGEST,
            "size_bytes": 10 + i,
            "instrument_code": str(1000 + i),
            "series_year": 2026,
        }
        for i in range(501)
    ]
    calls: list[int] = []

    def fake_rpc(name, body, timeout_s=None):
        assert name == "register_pending_derived_objects"
        assert timeout_s == adapter.BATCH_RPC_TIMEOUT_S
        chunk = body["p_objects"]
        calls.append(len(chunk))
        assert len(chunk) <= adapter.BATCH_OBJECT_CHUNK_SIZE
        return [
            {"object_key": item["object_key"], "object_id": f"id-{item['object_key']}"}
            for item in chunk
        ]

    with patch.object(adapter, "_rpc", fake_rpc):
        records = adapter.register_pending_objects(generation_id=GEN_ID, objects=objects)
    assert calls == [500, 1]
    assert len(records) == 501
    assert records[0].object_id == "id-k-0"
    assert adapter._object_ids_by_key[(GEN_ID, "k-0")] == "id-k-0"


def test_supabase_list_committed_series_keys_pages() -> None:
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
    )
    page1 = [{"instrument_code": f"{i}", "object_key": f"ok-{i}"} for i in range(1000)]
    page2 = [{"instrument_code": "9999", "object_key": "ok-9999"}]
    offsets: list[str] = []

    def fake_request(method, path, json_body=None, params=None, prefer=None, timeout_s=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        assert params["object_kind"] == "eq.series"
        assert params["status"] == "eq.committed"
        offsets.append(params["offset"])
        if params["offset"] == "0":
            return httpx.Response(200, json=page1, request=request)
        return httpx.Response(200, json=page2, request=request)

    with patch.object(adapter, "_request", fake_request):
        out = adapter.list_committed_series_keys(metric_set_version_id=SET_ID, series_year=2026)
    assert offsets == ["0", "1000"]
    assert out["0"] == "ok-0"
    assert out["9999"] == "ok-9999"


def test_supabase_stage_latest_chunks_500() -> None:
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
    )
    rows = [
        {
            "instrument_code": str(i),
            "trade_date": "2026-01-15",
            "values_json": {"alpha_metric": float(i)},
            "logical_digest": DIGEST,
        }
        for i in range(501)
    ]
    calls: list[int] = []

    def fake_rpc(name, body, timeout_s=None):
        assert name == "stage_latest_derived_observations"
        assert timeout_s == adapter.BATCH_RPC_TIMEOUT_S
        calls.append(len(body["p_rows"]))
        return len(body["p_rows"])

    with patch.object(adapter, "_rpc", fake_rpc):
        total = adapter.stage_latest_observations(generation_id=GEN_ID, rows=rows)
    assert calls == [500, 1]
    assert total == 501


def test_supabase_commit_generation_uses_long_timeout() -> None:
    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
    )
    seen: dict[str, object] = {}
    generation_row = {
        "id": GEN_ID,
        "metric_set_version_id": SET_ID,
        "trade_date": "2026-01-15",
        "mode": "backfill",
        "artifact_profile": ArtifactProfile.SNAPSHOT_SERIES.value,
        "repository": "org/repo",
        "workflow": "derived_backfill.yml",
        "github_run_id": 99,
        "status": "committed",
        "expected_old_digest": None,
        "declared_new_digest": DIGEST,
        "new_digest": DIGEST,
        "heartbeat_at": "2026-01-15T00:00:00+00:00",
        "created_at_utc": "2026-01-15T00:00:00+00:00",
        "committed_at_utc": "2026-01-15T00:01:00+00:00",
    }

    def fake_rpc(name, body, timeout_s=None):
        seen["name"] = name
        seen["timeout_s"] = timeout_s
        seen["body"] = body
        return None

    def fake_fetch(generation_id: str):
        assert generation_id == GEN_ID
        return generation_row

    with patch.object(adapter, "_rpc", fake_rpc), patch.object(
        adapter, "_fetch_generation_row", fake_fetch
    ):
        record = adapter.commit_generation(generation_id=GEN_ID, new_logical_digest=DIGEST)
    assert seen["name"] == "commit_derived_generation"
    assert seen["timeout_s"] == adapter.COMMIT_RPC_TIMEOUT_S
    assert adapter.COMMIT_RPC_TIMEOUT_S >= 180.0
    assert record.status == "committed"


def test_supabase_batch_rpc_missing_fails_fast() -> None:
    from stockradar.storage.derived_generation import GenerationConflictError

    adapter = SupabaseMetricGenerationAdapter(
        base_url="https://example.supabase.co",
        secret_key="secret",
    )

    def fake_request(method, path, json_body=None, params=None, prefer=None, timeout_s=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        return httpx.Response(
            404,
            text="Could not find the function public.register_pending_derived_objects",
            request=request,
        )

    with patch.object(adapter, "_request", fake_request):
        with pytest.raises(GenerationConflictError) as excinfo:
            adapter.register_pending_objects(
                generation_id=GEN_ID,
                objects=[
                    {
                        "object_kind": "series",
                        "object_key": "k",
                        "logical_digest": DIGEST,
                        "byte_sha256": DIGEST,
                        "size_bytes": 1,
                        "instrument_code": "1301",
                        "series_year": 2026,
                    }
                ],
            )
    assert "migration 008" in str(excinfo.value).lower()


def test_s3_r2_pool_tracks_concurrency_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("DERIVED_R2_CONCURRENCY", "32")
    store = S3R2ObjectStore.from_env()
    assert store.max_pool_connections >= 32
    assert hasattr(store, "warm_client")

