"""put-fixed idempotency and cache_key regression (Blocker 2)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stockradar.storage.supabase_client import FakeSupabaseControlAdapter
from stockradar.utils.manifest import compute_sha256

pytestmark = pytest.mark.unit

JPX_CACHE_KEY = "jpx-latest-url"
INDEX_CACHE_KEY = "index-store-zip-v1"
OHLC_CACHE_KEY = "ohlc-store-zip-v2"


def _put_fixed_args(tmp_path: Path, entry_id: str, zip_path: Path) -> object:
    import scripts.storage.cache_bus_cli as mod

    return mod.argparse.Namespace(
        entry_id=entry_id,
        local_path=str(zip_path),
        github_run_id="42",
        is_replay="false",
        phase3_rollout_stage="3c",
        json_output=str(tmp_path / f"{entry_id}.json"),
    )


def test_put_fixed_idempotent_noop_same_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "true")
    zip_path = tmp_path / "index_store.zip"
    zip_path.write_bytes(b"same-content")
    sha = compute_sha256(str(zip_path))

    import scripts.storage.cache_bus_cli as mod

    fake = FakeSupabaseControlAdapter()
    fake.cache_pointers[INDEX_CACHE_KEY] = {
        "cache_key": INDEX_CACHE_KEY,
        "sha256": sha,
        "object_key": "cache/index-store-zip-v1/index_store.zip",
        "size_bytes": len(b"same-content"),
    }
    monkeypatch.setattr(mod, "_adapter_supabase", lambda: fake)

    with patch.object(mod, "_r2") as mock_r2:
        put_object = MagicMock()
        mock_r2.return_value.put_object = put_object
        rc = mod.cmd_put_fixed(_put_fixed_args(tmp_path, "cache-index-store-zip-v1", zip_path))
        assert rc == 0
        payload = json.loads((tmp_path / "cache-index-store-zip-v1.json").read_text(encoding="utf-8"))
        assert payload.get("noop") is True
        put_object.assert_not_called()


def test_put_fixed_jpx_same_sha_does_not_noop_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: JPX pointer must not cause index/OHLC false noop."""
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "true")
    zip_path = tmp_path / "index_store.zip"
    zip_path.write_bytes(b"index-zip")
    sha = compute_sha256(str(zip_path))

    import scripts.storage.cache_bus_cli as mod

    fake = FakeSupabaseControlAdapter()
    fake.cache_pointers[JPX_CACHE_KEY] = {
        "cache_key": JPX_CACHE_KEY,
        "sha256": sha,
        "object_key": "cache/jpx-url/jpx_latest_url.txt",
        "size_bytes": 10,
    }
    monkeypatch.setattr(mod, "_adapter_supabase", lambda: fake)

    with patch.object(mod, "_r2") as mock_r2:
        put_object = MagicMock()
        mock_r2.return_value.put_object = put_object
        rc = mod.cmd_put_fixed(_put_fixed_args(tmp_path, "cache-index-store-zip-v1", zip_path))
        assert rc == 0
        payload = json.loads((tmp_path / "cache-index-store-zip-v1.json").read_text(encoding="utf-8"))
        assert payload.get("noop") is not True
        put_object.assert_called_once()
        assert fake.cache_pointers[INDEX_CACHE_KEY]["sha256"] == sha


def test_put_fixed_commits_correct_cache_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "true")
    zip_path = tmp_path / "ohlc_store.zip"
    zip_path.write_bytes(b"ohlc-v2")

    import scripts.storage.cache_bus_cli as mod

    fake = FakeSupabaseControlAdapter()
    monkeypatch.setattr(mod, "_adapter_supabase", lambda: fake)

    with patch.object(mod, "_r2") as mock_r2:
        mock_r2.return_value.put_object = lambda *a, **k: None
        rc = mod.cmd_put_fixed(_put_fixed_args(tmp_path, "cache-ohlc-store-zip-v2", zip_path))
        assert rc == 0
    assert OHLC_CACHE_KEY in fake.cache_pointers
    assert fake.cache_pointers[OHLC_CACHE_KEY]["sha256"] == compute_sha256(str(zip_path))


def test_fake_cache_pointer_default_and_version_cas() -> None:
    fake = FakeSupabaseControlAdapter()
    fake.commit_fixed_cache_rpc(
        cache_key=OHLC_CACHE_KEY,
        object_key="cache/ohlc_store.zip",
        sha256="a" * 64,
        size_bytes=10,
        writer_workflow="daily.yml",
        source_github_run_id=1,
        history_id=None,
    )
    assert fake.cache_pointers[OHLC_CACHE_KEY]["version"] == 1

    version = fake.commit_cache_pointer_cas_rpc(
        cache_key=OHLC_CACHE_KEY,
        expected_version=1,
        object_key="cache/ohlcv/objects/sha256=" + ("b" * 64) + ".zip",
        sha256="b" * 64,
        size_bytes=11,
        writer_workflow="daily.yml",
        source_github_run_id=2,
    )
    assert version == 2
    assert fake.cache_pointers[OHLC_CACHE_KEY]["version"] == 2

    with pytest.raises(RuntimeError, match="cache_pointer_cas_conflict"):
        fake.commit_cache_pointer_cas_rpc(
            cache_key=OHLC_CACHE_KEY,
            expected_version=1,
            object_key="cache/ohlcv/objects/stale.zip",
            sha256="c" * 64,
            size_bytes=12,
            writer_workflow="monthly_new_core_backfill.yml",
            source_github_run_id=3,
        )


def test_fake_jpx_commit_remains_legacy_compatible() -> None:
    fake = FakeSupabaseControlAdapter()
    fake.commit_jpx_url_cache_rpc(
        object_key="cache/jpx-url/jpx_latest_url.txt",
        sha256="d" * 64,
        size_bytes=20,
        writer_workflow="monthly.yml",
        source_github_run_id=4,
        history_id=None,
    )
    assert fake.cache_pointers[JPX_CACHE_KEY]["version"] == 1
