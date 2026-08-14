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

    def fake_request(method, path, json_body=None, params=None, prefer=None):
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

    def fake_request(method, path, json_body=None, params=None, prefer=None):
        request = httpx.Request(method, f"https://example.supabase.co{path}")
        assert path.endswith("/active_metric_set")
        return httpx.Response(200, json=[{"metric_set_version_id": SET_ID}], request=request)

    with patch.object(adapter, "_request", fake_request):
        assert adapter.get_active_metric_set_id() == SET_ID
