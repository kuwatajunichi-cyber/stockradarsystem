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
from stockradar.storage.handoff_summary import write_producer_summary, write_summary

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
    assert payload["r2_put_ok"] is True
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


def test_required_get_r2_missing_emits_fallback_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    json_out = tmp_path / "get.json"
    rc = main(
        [
            "get",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(tmp_path / "core.csv"),
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 1
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["fallback_required"] is True
    assert payload["handoff_source"] is None
    assert payload["status"] in {"r2_missing", "r2_error"}


def test_get_success_includes_handoff_source(tmp_path: Path, _fake_adapter: FakeR2StagingAdapter) -> None:
    blob = tmp_path / "core.csv"
    blob.write_text("code,name\n1,foo\n", encoding="utf-8")
    out_path = tmp_path / "restored.csv"
    json_out = tmp_path / "get.json"
    assert (
        main(
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
        == 0
    )
    rc = main(
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
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["handoff_source"] == "r2"
    assert payload["fallback_required"] is False
    assert payload["validated_count"] == 1


def test_record_fallback_required_success(tmp_path: Path) -> None:
    blob = tmp_path / "core.csv"
    blob.write_text("code,name\n1,foo\n", encoding="utf-8")
    json_out = tmp_path / "fallback.json"
    rc = main(
        [
            "record-fallback",
            "--entry-id",
            "artifact-daily-core-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(blob),
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["handoff_source"] == "github_fallback"
    assert payload["fallback_used"] is True
    assert payload["validated_count"] == 1


def test_record_fallback_optional_missing_is_success(tmp_path: Path) -> None:
    json_out = tmp_path / "fallback.json"
    rc = main(
        [
            "record-fallback",
            "--entry-id",
            "artifact-enriched-csv",
            "--run-id",
            "555",
            "--run-date",
            "2026-06-13",
            "--local-path",
            str(tmp_path / "missing.csv"),
            "--json-output",
            str(json_out),
        ]
    )
    assert rc == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped_optional_missing"


def test_write_handoff_summary_required_ok_with_github_fallback(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "artifact-daily-core-csv.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "entry_id": "artifact-daily-core-csv",
                "handoff_source": "github_fallback",
                "fallback_used": True,
                "sha256": "abc",
                "validated_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_summary(
        handoff_dir=handoff_dir,
        title="test handoff",
        required=["artifact-daily-core-csv"],
        optional=[],
    )
    assert exit_code == 0
    assert any("fallback_used" in line for line in lines)


def test_write_handoff_summary_required_failure_when_missing(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    lines, exit_code = write_summary(
        handoff_dir=handoff_dir,
        title="test handoff",
        required=["artifact-daily-core-csv"],
        optional=[],
    )
    assert exit_code == 1
    assert any("missing_handoff_record" in line for line in lines)


def test_write_handoff_summary_required_fails_on_skipped_optional_missing(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "artifact-daily-core-csv.json").write_text(
        json.dumps(
            {
                "status": "skipped_optional_missing",
                "entry_id": "artifact-daily-core-csv",
                "degraded_reason": "optional_local_missing",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_summary(
        handoff_dir=handoff_dir,
        title="test handoff",
        required=["artifact-daily-core-csv"],
        optional=[],
    )
    assert exit_code == 1
    assert any("handoff_failed_required" in line for line in lines)


def test_write_handoff_summary_optional_skipped_is_ok(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "artifact-stale-exclusions.json").write_text(
        json.dumps(
            {
                "status": "skipped_optional_missing",
                "entry_id": "artifact-stale-exclusions",
                "degraded_reason": "optional_local_missing",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_summary(
        handoff_dir=handoff_dir,
        title="test handoff",
        required=[],
        optional=["artifact-stale-exclusions"],
    )
    assert exit_code == 0
    assert any("skipped_optional" in line for line in lines)


def test_write_producer_summary_degraded_when_r2_put_failed_but_github_ok(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "producer"
    handoff_dir.mkdir()
    (handoff_dir / "artifact-daily-core-csv.json").write_text(
        json.dumps(
            {
                "status": "r2_error",
                "entry_id": "artifact-daily-core-csv",
                "r2_put_ok": False,
                "degraded_reason": "r2_put_failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_producer_summary(
        handoff_dir=handoff_dir,
        title="test producer",
        required=["artifact-daily-core-csv"],
        optional=[],
        github_upload_ok=frozenset({"artifact-daily-core-csv"}),
    )
    assert exit_code == 0
    assert any("producer_handoff_status=`degraded`" in line for line in lines)
    assert any("producer_degraded" in line for line in lines)


def test_write_producer_summary_fails_when_r2_and_github_both_failed(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "producer"
    handoff_dir.mkdir()
    (handoff_dir / "artifact-daily-core-csv.json").write_text(
        json.dumps(
            {
                "status": "r2_error",
                "entry_id": "artifact-daily-core-csv",
                "r2_put_ok": False,
                "degraded_reason": "r2_put_failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_producer_summary(
        handoff_dir=handoff_dir,
        title="test producer",
        required=["artifact-daily-core-csv"],
        optional=[],
        github_upload_ok=frozenset(),
    )
    assert exit_code == 1
    assert any("producer_handoff_failed_required" in line for line in lines)


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
