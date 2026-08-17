"""Contract: canonical flags, ordinal series keys, manifests, set_key, R2 endpoint."""
from __future__ import annotations

import json

import pytest

from stockradar.jobs.write_derived_generation import (
    DerivedGenerationRequest,
    SnapshotInput,
    run_derived_generation,
)
from stockradar.metrics.registry_spec import load_metric_set_spec
from stockradar.metrics.seed_catalog import SET_KEY_PATTERN, build_metric_set_seed_payload
from stockradar.storage.derived_generation import FakeMetricGenerationStore
from stockradar.storage.derived_series import gunzip_series_bytes, parse_series_canonical_bytes
from stockradar.storage.derived_snapshot import SNAPSHOT_MANIFEST_FIELD_ORDER, LATEST_FLAGS_KEY
from stockradar.storage.derived_leftover import leftover_scan_prefixes
from stockradar.storage.r2_object_store import FakeR2ObjectStore, normalize_r2_s3_endpoint

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
SHA = "c" * 64
FP = "d" * 64


def _run(*, keys: list[str], values: dict[str, dict[str, object]], stage: str = "4.5b"):
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    snapshot_input = SnapshotInput(
        metric_keys_ordered=keys,
        metric_types={key: "float" for key in keys},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage=stage,
        mode="normal",
        trade_date="2026-01-15",
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=9,
        metric_set_version_id=SET_ID,
        active_metric_set_id=SET_ID if stage == "4.5c" else None,
        lifecycle_status="active" if stage == "4.5c" else "shadow",
        is_active=stage == "4.5c",
        is_current_latest_trade_date=stage == "4.5c",
        set_fingerprint=FP,
    )
    latest_rows = None
    if stage == "4.5c":
        latest_rows = [
            {
                "instrument_code": code,
                "trade_date": "2026-01-15",
                "values_json": payload,
                "logical_digest": "a" * 64,
            }
            for code, payload in values.items()
        ]
    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=store,
        r2_store=r2,
        latest_rows=latest_rows,
    )
    return result, store, r2


def test_series_keys_follow_metric_set_ordinal_not_alpha() -> None:
    keys = ["zeta_metric", "alpha_metric"]
    result, store, r2 = _run(keys=keys, values={"1301": {"zeta_metric": 1.0, "alpha_metric": 2.0}})
    assert result.exit_code == 0
    object_key = store.get_committed_series_object_key(
        metric_set_version_id=SET_ID,
        instrument_code="1301",
        series_year=2026,
    )
    assert object_key is not None
    _dates, series, flags = parse_series_canonical_bytes(gunzip_series_bytes(r2.get_object(object_key)))
    assert list(series) == keys
    assert flags[0]["missing_metrics"] == []
    assert flags[0]["non_finite_metrics"] == []
    assert flags[0]["po_indeterminate"] is False


def test_snapshot_and_series_manifests_are_indexed() -> None:
    result, store, r2 = _run(keys=["alpha_metric"], values={"1301": {"alpha_metric": 1.0}})
    assert result.exit_code == 0
    pending = store.list_pending_objects(result.generation_id)
    kinds = {row.object_kind for row in pending}
    assert kinds == {"snapshot", "snapshot_manifest", "series", "series_manifest"}
    gen = store.generations[result.generation_id]
    assert gen["expected_object_count"] == 4
    assert gen["expected_object_set_digest"]
    manifest_key = next(row.object_key for row in pending if row.object_kind == "snapshot_manifest")
    payload = json.loads(r2.get_object(manifest_key).decode("utf-8"))
    assert list(payload) == list(SNAPSHOT_MANIFEST_FIELD_ORDER)
    assert payload["set_fingerprint"] == FP
    assert payload["source_github_run_id"] == 9
    assert payload["row_count"] == 1
    assert payload["metric_keys_ordered"] == ["alpha_metric"]
    assert payload["mode"] == "normal"
    assert payload["writer_version"]
    assert payload["serialization"]["format"] == "parquet"


def test_path_b_set_key_matches_fingerprint_contract() -> None:
    spec = load_metric_set_spec()
    from stockradar.metrics.registry_spec import default_metric_set_v1_free_path

    free = load_metric_set_spec(default_metric_set_v1_free_path())
    payload = build_metric_set_seed_payload(free)
    assert SET_KEY_PATTERN.match(payload["set_key"])
    assert payload["set_key"] == free.set_key
    assert payload["lifecycle_status"] == "draft"
    assert len(payload["members"]) == 13
    assert spec.set_key != free.set_key


def test_normalize_r2_endpoint_strips_bucket_path() -> None:
    url = normalize_r2_s3_endpoint(
        "https://abc.r2.cloudflarestorage.com/stock-radar-system",
        account_id="abc",
        bucket="stock-radar-system",
    )
    assert url == "https://abc.r2.cloudflarestorage.com"


def test_leftover_scan_includes_forbidden_shadow_and_failed_manifest_prefix() -> None:
    prefixes = leftover_scan_prefixes(
        metric_set_version_id=SET_ID,
        trade_date="2026-08-14",
        generation_id="56004f01-137a-414a-bd71-b8d1fae3168e",
    )
    assert "derived-shadow/" in prefixes
    assert any("generation=56004f01-137a-414a-bd71-b8d1fae3168e/" in item for item in prefixes)


def test_latest_rows_embed_canonical_flags() -> None:
    result, store, _r2 = _run(
        keys=["alpha_metric"],
        values={"1301": {"alpha_metric": 1.0}},
        stage="4.5c",
    )
    assert result.exit_code == 0
    committed = store.committed_latest_observations[(SET_ID, "1301")]
    flags = committed["values_json"][LATEST_FLAGS_KEY]
    assert flags["missing_metrics"] == []
    assert "alpha_metric" in committed["values_json"]
