from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.storage.artifact_bus import (
    RUN_ARTIFACT_MANIFEST_KIND,
    RUN_ARTIFACT_SCHEMA_VERSION,
    create_run_artifact_manifest,
    enriched_csv_basename,
    indicators_csv_basename,
    manifest_logical_key,
    resolve_entry_logical_key,
    resolve_logical_key,
    verify_run_artifact_manifest,
)
from stockradar.storage.mapping_catalog import get_entry, phase2_daily_artifact_entry_ids
from stockradar.utils.manifest import compute_sha256

pytestmark = pytest.mark.unit


def test_resolve_logical_key_run_id_and_run_date_compact() -> None:
    pattern = "runs/daily/{run_id}/artifacts/daily-indicators/indicators_{run_date_compact}.csv"
    key = resolve_logical_key(pattern, run_id="999", run_date="2026-06-13")
    assert key == "runs/daily/999/artifacts/daily-indicators/indicators_20260613.csv"


def test_resolve_entry_logical_key_for_core_csv() -> None:
    key = resolve_entry_logical_key(
        "artifact-daily-core-csv", run_id="123", run_date="2026-06-13"
    )
    assert key.endswith("equity_domestic_core_with_name.csv")


def test_manifest_logical_key_slug() -> None:
    assert manifest_logical_key("artifact-daily-core-csv", "42") == (
        "runs/daily/42/manifests/daily-core-csv.json"
    )


def test_unknown_placeholder_fail_fast() -> None:
    with pytest.raises(ValueError, match="unknown placeholder"):
        resolve_logical_key("runs/{unknown}/x", run_id="1", run_date="2026-06-13")


def test_create_and_verify_run_artifact_manifest(tmp_path: Path) -> None:
    blob = tmp_path / "data.csv"
    blob.write_bytes(b"a,b\n1,2\n")
    manifest = create_run_artifact_manifest(
        entry_id="artifact-daily-indicators",
        source_name="daily-indicators-2026-06-13",
        logical_object_key="runs/daily/1/artifacts/daily-indicators/indicators_20260613.csv",
        local_path=str(blob),
        content_type="text/csv",
        optional=False,
        github_run_id="1",
        run_date="2026-06-13",
    )
    assert manifest["manifest_kind"] == RUN_ARTIFACT_MANIFEST_KIND
    assert manifest["run_artifact_schema_version"] == RUN_ARTIFACT_SCHEMA_VERSION
    sha = compute_sha256(blob)
    ok, msg = verify_run_artifact_manifest(
        manifest, content_sha256=sha, size_bytes=blob.stat().st_size
    )
    assert ok, msg


def test_indicators_basename_matches_mapping() -> None:
    run_date = "2026-06-13"
    assert indicators_csv_basename(run_date) == "indicators_20260613.csv"
    key = resolve_entry_logical_key(
        "artifact-daily-indicators", run_id="9", run_date=run_date
    )
    assert key.endswith(indicators_csv_basename(run_date))
    enriched = resolve_entry_logical_key(
        "artifact-enriched-csv", run_id="9", run_date=run_date
    )
    assert enriched.endswith(enriched_csv_basename(run_date))


@pytest.mark.parametrize("entry_id", phase2_daily_artifact_entry_ids())
def test_phase2_entries_have_structured_optional(entry_id: str) -> None:
    entry = get_entry(entry_id)
    assert "optional" in entry
    assert isinstance(entry["optional"], bool)


def test_stale_and_enriched_optional_flags() -> None:
    assert get_entry("artifact-stale-exclusions")["optional"] is True
    assert get_entry("artifact-enriched-csv")["optional"] is True
    assert get_entry("artifact-daily-core-csv")["optional"] is False
