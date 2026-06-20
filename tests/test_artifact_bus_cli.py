from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.storage.artifact_bus_cli import main
from scripts.storage.fake_r2_staging import FakeR2StagingAdapter
from scripts.storage import artifact_bus_cli
from scripts.storage.runs_staging_cleanup import (
    batch_object_keys,
    cleanup_runs_staging_objects,
    select_stale_object_keys,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fake_adapter(monkeypatch: pytest.MonkeyPatch) -> FakeR2StagingAdapter:
    fake = FakeR2StagingAdapter()

    def _from_env() -> FakeR2StagingAdapter:
        return fake

    monkeypatch.setattr(artifact_bus_cli, "_adapter_from_env", _from_env)
    return fake


def test_put_and_get_roundtrip(tmp_path: Path) -> None:
    blob = tmp_path / "core.csv"
    blob.write_text("code,name\n1,foo\n", encoding="utf-8")
    out_path = tmp_path / "restored.csv"

    rc_put = main(
        [
            "put",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--source-name",
            "daily-core-csv-555",
            "--local-path",
            str(blob),
        ]
    )
    assert rc_put == 0

    rc_get = main(
        [
            "get",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(out_path),
        ]
    )
    assert rc_get == 0
    assert out_path.read_text(encoding="utf-8") == blob.read_text(encoding="utf-8")


def test_put_writes_manifest_key_to_json_output(tmp_path: Path) -> None:
    blob = tmp_path / "core.csv"
    blob.write_text("code,name\n1,foo\n", encoding="utf-8")
    json_out = tmp_path / "put.json"

    rc = main(
        [
            "put",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--source-name",
            "daily-core-csv-555",
            "--local-path",
            str(blob),
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["manifest_logical_key"] == "runs/daily/555/manifests/daily-core-csv.json"


def test_optional_missing_file_put_is_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.json"
    rc = main(
        [
            "put",
            "--entry-id",
            "artifact-stale-exclusions",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--source-name",
            "stale-exclusions-555",
            "--local-path",
            str(missing),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "skipped_optional_missing"
    assert payload["validated_count"] == 0


def test_required_missing_file_put_fails(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    rc = main(
        [
            "put",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--source-name",
            "daily-core-csv-555",
            "--local-path",
            str(missing),
        ]
    )
    assert rc == 1


def test_optional_missing_get_is_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "get",
            "--entry-id",
            "artifact-stale-exclusions",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(tmp_path / "missing.json"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "skipped_optional_missing"


def test_shadow_validate_detects_mismatch(tmp_path: Path, _fake_adapter: FakeR2StagingAdapter) -> None:
    local_a = tmp_path / "a.csv"
    local_b = tmp_path / "b.csv"
    local_a.write_text("a\n", encoding="utf-8")
    local_b.write_text("b\n", encoding="utf-8")

    assert (
        main(
            [
                "put",
                "--entry-id",
                "artifact-daily-indicators",
                "--run-id",
                "777",
                "--run-date",
                "2026-06-13",
                "--source-name",
                "daily-indicators-2026-06-13",
                "--local-path",
                str(local_a),
            ]
        )
        == 0
    )

    rc = main(
        [
            "shadow-validate",
            "--entry-id",
            "artifact-daily-indicators",
            "--run-id",
            "777",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(local_b),
        ]
    )
    assert rc == 1


def test_shadow_validate_optional_missing_local_is_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    local_path = tmp_path / "missing.csv"
    rc = main(
        [
            "shadow-validate",
            "--entry-id",
            "artifact-enriched-csv",
            "--run-id",
            "777",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(local_path),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "skipped_optional_missing"
    assert payload["degraded_reason"] == "optional_local_missing"


def test_shadow_validate_optional_local_present_r2_missing_fails(tmp_path: Path) -> None:
    local_path = tmp_path / "enriched.csv"
    local_path.write_text("code,news\n1,event\n", encoding="utf-8")
    rc = main(
        [
            "shadow-validate",
            "--entry-id",
            "artifact-enriched-csv",
            "--run-id",
            "777",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(local_path),
        ]
    )
    assert rc == 1


def test_shadow_validate_success_writes_json_output(tmp_path: Path) -> None:
    local_path = tmp_path / "same.csv"
    local_path.write_text("a\n", encoding="utf-8")
    json_out = tmp_path / "shadow_ok.json"

    assert (
        main(
            [
                "put",
                "--entry-id",
                "artifact-daily-indicators",
                "--run-id",
                "777",
                "--run-date",
                "2026-06-13",
                "--source-name",
                "daily-indicators-2026-06-13",
                "--local-path",
                str(local_path),
            ]
        )
        == 0
    )

    rc = main(
        [
            "shadow-validate",
            "--entry-id",
            "artifact-daily-indicators",
            "--run-id",
            "777",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(local_path),
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["validated_count"] == 1


def test_select_stale_object_keys_respects_cutoff() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    objects = [
        {"Key": "old", "LastModified": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        {"Key": "new", "LastModified": datetime(2026, 6, 15, tzinfo=timezone.utc)},
    ]
    selected = select_stale_object_keys(objects, cutoff=cutoff)
    assert selected == [{"Key": "old"}]


def test_batch_object_keys_splits_at_1000() -> None:
    keys = [{"Key": f"k{i}"} for i in range(1001)]
    batches = batch_object_keys(keys, batch_size=1000)
    assert len(batches) == 2
    assert len(batches[0]) == 1000
    assert len(batches[1]) == 1


def test_cleanup_runs_staging_objects_dry_run() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    objects = [
        {"Key": "old", "LastModified": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        {"Key": "new", "LastModified": datetime(2026, 6, 15, tzinfo=timezone.utc)},
    ]
    deleted_batches: list[list[dict[str, str]]] = []

    class FakeDeleter:
        def delete_objects(self, *, bucket: str, objects: list[dict[str, str]]) -> None:
            deleted_batches.append(objects)

    count = cleanup_runs_staging_objects(
        objects=objects,
        cutoff=cutoff,
        dry_run=True,
        deleter=FakeDeleter(),
        bucket="bucket",
    )
    assert count == 1
    assert deleted_batches == []


def test_cleanup_runs_staging_objects_deletes_in_batches() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    objects = [
        {"Key": f"old{i}", "LastModified": datetime(2026, 5, 1, tzinfo=timezone.utc)}
        for i in range(1001)
    ]
    deleted_batches: list[list[dict[str, str]]] = []

    class FakeDeleter:
        def delete_objects(self, *, bucket: str, objects: list[dict[str, str]]) -> None:
            deleted_batches.append(objects)

    count = cleanup_runs_staging_objects(
        objects=objects,
        cutoff=cutoff,
        dry_run=False,
        deleter=FakeDeleter(),
        bucket="bucket",
    )
    assert count == 1001
    assert len(deleted_batches) == 2
    assert len(deleted_batches[0]) == 1000
    assert len(deleted_batches[1]) == 1


def test_r2_staging_physical_key_strips_bucket_prefix() -> None:
    from scripts.storage.r2_staging_client import R2StagingAdapter

    adapter = R2StagingAdapter(
        bucket="my-bucket",
        base_prefix="my-bucket/prod/",
        access_key_id="x",
        secret_access_key="y",
        account_id="z",
        endpoint_url="https://example.com",
    )
    assert adapter._physical_key("runs/daily/1/a.csv") == "prod/runs/daily/1/a.csv"


def test_r2_staging_physical_key_normalizes_trailing_slash() -> None:
    from scripts.storage.r2_staging_client import R2StagingAdapter

    adapter = R2StagingAdapter(
        bucket="my-bucket",
        base_prefix="prod",
        access_key_id="x",
        secret_access_key="y",
        account_id="z",
        endpoint_url="https://example.com",
    )
    assert adapter._physical_key("runs/daily/1/a.csv") == "prod/runs/daily/1/a.csv"
