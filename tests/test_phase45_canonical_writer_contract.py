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
from stockradar.storage.derived_series import (
    VALID_SERIES_PROVENANCE,
    build_series_manifest_bytes,
    gunzip_series_bytes,
    parse_series_canonical_bytes,
    series_provenance_for_run_mode,
)
from stockradar.storage.derived_snapshot import SNAPSHOT_MANIFEST_FIELD_ORDER, LATEST_FLAGS_KEY
from stockradar.storage.derived_leftover import leftover_scan_prefixes
from stockradar.storage.r2_object_store import FakeR2ObjectStore, normalize_r2_s3_endpoint

pytestmark = pytest.mark.unit

SET_ID = "11111111-2222-3333-4444-555555555555"
SHA = "c" * 64
FP = "d" * 64


def _run(
    *,
    keys: list[str],
    values: dict[str, dict[str, object]],
    stage: str = "4.5b",
    mode: str = "normal",
):
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    active_path = stage == "4.5c" and mode != "backfill"
    snapshot_input = SnapshotInput(
        metric_keys_ordered=keys,
        metric_types={key: "float" for key in keys},
        values_by_instrument=values,
        layer1_input_fingerprint=SHA,
    )
    request = DerivedGenerationRequest(
        stage=stage,
        mode=mode,
        trade_date="2026-01-15",
        repository="org/repo",
        workflow="derived_writer",
        github_run_id=9,
        metric_set_version_id=SET_ID,
        active_metric_set_id=SET_ID if active_path else None,
        lifecycle_status="active" if active_path else "shadow",
        is_active=active_path,
        is_current_latest_trade_date=active_path,
        set_fingerprint=FP,
    )
    latest_rows = None
    if active_path:
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


def _series_manifest_payload(store: FakeMetricGenerationStore, r2: FakeR2ObjectStore, generation_id: str) -> dict:
    pending = store.list_pending_objects(generation_id)
    key = next(row.object_key for row in pending if row.object_kind == "series_manifest")
    payload = json.loads(r2.get_object(key).decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


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


def test_series_provenance_maps_run_mode_and_rejects_unknown() -> None:
    assert series_provenance_for_run_mode("normal") == "daily_normal"
    assert series_provenance_for_run_mode("backfill") == "backfill"
    assert series_provenance_for_run_mode("reconcile") == "reconcile"
    assert series_provenance_for_run_mode("series_seed") == "series_seed"
    assert series_provenance_for_run_mode("series_repair") == "series_repair"
    assert set(series_provenance_for_run_mode(mode) for mode in ("normal", "backfill", "reconcile", "series_seed", "series_repair")) <= VALID_SERIES_PROVENANCE
    with pytest.raises(ValueError, match="unsupported run mode"):
        series_provenance_for_run_mode("replay")
    with pytest.raises(ValueError, match="unsupported run mode"):
        series_provenance_for_run_mode("not-a-mode")


def test_unknown_series_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="series manifest provenance required"):
        build_series_manifest_bytes(
            instrument_code="1301",
            year=2026,
            metric_set_version_id=SET_ID,
            generation_id="56004f01-137a-414a-bd71-b8d1fae3168e",
            logical_digest="a" * 64,
            object_sha256="b" * 64,
            object_size=1,
            writer_workflow="derived_writer",
            set_fingerprint=FP,
            source_github_run_id=9,
            row_count=1,
            metric_keys_ordered=["alpha_metric"],
            mode="normal",
            provenance="not-a-provenance",
        )


def test_reconcile_write_embeds_reconcile_series_provenance() -> None:
    result, store, r2 = _run(
        keys=["alpha_metric"],
        values={"1301": {"alpha_metric": 1.0}},
        stage="4.5c",
        mode="reconcile",
    )
    assert result.exit_code == 0
    assert result.generation_id is not None
    payload = _series_manifest_payload(store, r2, result.generation_id)
    assert payload["mode"] == "reconcile"
    assert payload["provenance"] == "reconcile"


def test_backfill_write_embeds_backfill_series_provenance() -> None:
    result, store, r2 = _run(
        keys=["alpha_metric"],
        values={"1301": {"alpha_metric": 1.0}},
        stage="4.5c",
        mode="backfill",
    )
    assert result.exit_code == 0
    assert result.generation_id is not None
    payload = _series_manifest_payload(store, r2, result.generation_id)
    assert payload["mode"] == "backfill"
    assert payload["provenance"] == "backfill"


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
