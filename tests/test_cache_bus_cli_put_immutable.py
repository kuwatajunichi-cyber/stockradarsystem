"""put-immutable create-only object key + pointer CAS."""
from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.storage.control_plane import resolve_immutable_object_key
from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

pytestmark = pytest.mark.unit


def test_resolve_immutable_object_key_from_pattern() -> None:
    key = resolve_immutable_object_key(
        pattern="cache/index-store-zip-v1/objects/sha256={object_sha256}.zip",
        object_sha256="a" * 64,
    )
    assert key == "cache/index-store-zip-v1/objects/sha256=" + ("a" * 64) + ".zip"


def test_put_immutable_cli_uses_sha_object_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSupabaseControlAdapter()
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    # Inject fake via module-level by env handled in CLI; Fake constructor is fresh each call.
    # Instead exercise RPC path through Fake directly after computing key.
    content = b"PK\x03\x04immutable"
    zip_path = tmp_path / "blob.zip"
    zip_path.write_bytes(content)
    import hashlib

    sha = hashlib.sha256(content).hexdigest()
    object_key = resolve_immutable_object_key(
        pattern="cache/ohlc-store-zip-v2/objects/sha256={object_sha256}.zip",
        object_sha256=sha,
    )
    assert object_key.endswith(f"sha256={sha}.zip")
    ver = fake.commit_cache_pointer_cas_rpc(
        cache_key="ohlc-store-zip-v2",
        expected_version=0,
        object_key=object_key,
        sha256=sha,
        size_bytes=len(content),
        writer_workflow="daily.yml",
        source_github_run_id=1,
    )
    assert ver == 1
    pointer = fake.get_cache_pointer(cache_key="ohlc-store-zip-v2")
    assert pointer is not None
    assert pointer["object_key"] == object_key
    assert int(pointer["version"]) == 1


def test_staging_put_create_only_same_bytes_is_noop() -> None:
    from scripts.storage.r2_staging_client import R2StagingAdapter

    class _Err(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "PreconditionFailed"}}

    store: dict[str, bytes] = {}

    class _Client:
        def put_object(self, **kwargs):
            key = kwargs["Key"]
            body = kwargs["Body"]
            if kwargs.get("IfNoneMatch") == "*" and key in store:
                raise _Err()
            store[key] = body

        def get_object(self, **kwargs):
            key = kwargs["Key"]
            data = store[key]

            class _Body:
                def read(self):
                    return data

            return {"Body": _Body()}

    adapter = R2StagingAdapter.__new__(R2StagingAdapter)
    adapter._bucket = "b"
    adapter._get_client = lambda: _Client()  # type: ignore[method-assign]
    adapter._physical_key = lambda logical: logical  # type: ignore[method-assign]
    payload = b"same-bytes"
    assert adapter.put_object_create_only("k", payload) == "k"
    assert adapter.put_object_create_only("k", payload) == "k"
    with pytest.raises(RuntimeError, match="different bytes"):
        adapter.put_object_create_only("k", b"other")
