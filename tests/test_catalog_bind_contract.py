"""YAML catalog must match the resolved metric_set UUID fingerprint."""
from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.metrics.catalog_bind import (
    CatalogYamlMismatchError,
    FIRST_LIVE_ACTIVE_YAML_NAME,
    inherited_definition_fingerprints_match,
    load_and_bind,
    require_yaml_matches_registry,
    yaml_path_for_set_fingerprint,
)
from stockradar.metrics.registry_spec import load_metric_set_spec

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_V11 = _REPO / "config" / "metrics" / "metric_set_v1_1.yaml"
_V1 = _REPO / "config" / "metrics" / "metric_set_v1.yaml"
_V1_FREE = _REPO / "config" / "metrics" / "metric_set_v1_free.yaml"


def test_first_live_active_yaml_is_full_v11() -> None:
    assert FIRST_LIVE_ACTIVE_YAML_NAME == "metric_set_v1_1.yaml"
    spec = load_metric_set_spec(_V11)
    assert spec.set_family == "daily_core_v1_1"
    assert "rs_sma75_topix" in spec.metric_keys_ordered


def test_matching_fingerprint_binds() -> None:
    spec = load_metric_set_spec(_V11)
    row = {
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "set_fingerprint": spec.set_fingerprint,
        "set_key": spec.set_key,
        "metric_keys_ordered": spec.metric_keys_ordered,
    }
    require_yaml_matches_registry(spec, row, require_fingerprint=True)
    bound = load_and_bind(_V11, row, require_fingerprint=True)
    assert bound.set_fingerprint == spec.set_fingerprint


def test_v1_free_yaml_rejected_against_v11_fingerprint() -> None:
    v11 = load_metric_set_spec(_V11)
    free = load_metric_set_spec(_V1_FREE)
    row = {
        "set_fingerprint": v11.set_fingerprint,
        "set_key": v11.set_key,
    }
    with pytest.raises(CatalogYamlMismatchError, match="fingerprint"):
        require_yaml_matches_registry(free, row, require_fingerprint=True)


def test_yaml_path_for_fingerprint_is_unique_per_canonical_file() -> None:
    seen: set[str] = set()
    for name in (
        "metric_set_v1.yaml",
        "metric_set_v1_free.yaml",
        "metric_set_v1_1.yaml",
        "metric_set_v1_1_free.yaml",
    ):
        spec = load_metric_set_spec(_REPO / "config" / "metrics" / name)
        assert spec.set_fingerprint not in seen
        seen.add(spec.set_fingerprint)
        resolved = yaml_path_for_set_fingerprint(spec.set_fingerprint)
        assert resolved.name == name


def test_v11_inherits_v1_definition_fingerprints() -> None:
    v1 = load_metric_set_spec(_V1)
    v11 = load_metric_set_spec(_V11)
    assert inherited_definition_fingerprints_match(v1, v11) == []
    assert set(v1.metric_keys_ordered).issubset(set(v11.metric_keys_ordered))


def test_unknown_fingerprint_fails_closed() -> None:
    with pytest.raises(CatalogYamlMismatchError, match="no canonical YAML"):
        yaml_path_for_set_fingerprint("ab" * 32)
