"""Fail-fast bind: resolved metric_set UUID must match the YAML catalog fingerprint."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from stockradar.metrics.registry_spec import MetricSetSpec, load_metric_set_spec

CANONICAL_YAML_NAMES: frozenset[str] = frozenset(
    {
        "metric_set_v1.yaml",
        "metric_set_v1_free.yaml",
        "metric_set_v1_1.yaml",
        "metric_set_v1_1_free.yaml",
    }
)

FIRST_LIVE_ACTIVE_YAML_NAME = "metric_set_v1_1.yaml"


class CatalogYamlMismatchError(ValueError):
    """YAML catalog does not match the resolved metric_set_version row."""


def catalog_yaml_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "metrics"


def yaml_path_for_set_fingerprint(fingerprint: str) -> Path:
    """Pick the unique canonical YAML whose set_fingerprint matches the registry row."""
    target = fingerprint.strip().lower()
    if len(target) != 64 or any(ch not in "0123456789abcdef" for ch in target):
        raise CatalogYamlMismatchError(
            "metric_set_yaml_mismatch: set_fingerprint must be 64 hex chars"
        )
    hits: list[Path] = []
    for name in sorted(CANONICAL_YAML_NAMES):
        path = catalog_yaml_dir() / name
        spec = load_metric_set_spec(path)
        if spec.set_fingerprint.strip().lower() == target:
            hits.append(path)
    if not hits:
        raise CatalogYamlMismatchError(
            "metric_set_yaml_mismatch: no canonical YAML for set_fingerprint"
        )
    if len(hits) > 1:
        raise CatalogYamlMismatchError(
            "metric_set_yaml_mismatch: multiple canonical YAML for set_fingerprint"
        )
    return hits[0]


def yaml_path_for_registry_row(registry_row: Mapping[str, Any]) -> Path:
    path = yaml_path_for_set_fingerprint(str(registry_row.get("set_fingerprint") or ""))
    spec = load_metric_set_spec(path)
    require_yaml_matches_registry(spec, registry_row, require_fingerprint=True)
    return path


def inherited_definition_fingerprints_match(
    baseline: MetricSetSpec, candidate: MetricSetSpec
) -> list[str]:
    """Return metric_keys whose definition_fingerprint diverged from baseline."""
    baseline_fps = {m.metric_key: m.definition_fingerprint for m in baseline.members}
    mismatches: list[str] = []
    for member in candidate.members:
        old = baseline_fps.get(member.metric_key)
        if old is not None and old != member.definition_fingerprint:
            mismatches.append(member.metric_key)
    return mismatches


def require_canonical_yaml_path(path: Path) -> None:
    name = path.name
    if name not in CANONICAL_YAML_NAMES:
        raise CatalogYamlMismatchError(
            f"metric_set_yaml_mismatch: unsupported catalog file {name!r}"
        )


def require_yaml_matches_registry(
    spec: MetricSetSpec,
    registry_row: Mapping[str, Any],
    *,
    require_fingerprint: bool,
) -> None:
    require_canonical_yaml_path(spec.path)
    yaml_fp = spec.set_fingerprint.strip().lower()
    db_fp = str(registry_row.get("set_fingerprint") or "").strip().lower()
    if require_fingerprint and not db_fp:
        raise CatalogYamlMismatchError(
            "metric_set_yaml_mismatch: registry set_fingerprint missing"
        )
    if db_fp and db_fp != yaml_fp:
        raise CatalogYamlMismatchError(
            "metric_set_yaml_mismatch: definition_fingerprint / set_fingerprint"
        )
    db_key = str(registry_row.get("set_key") or "").strip()
    if db_key and db_key != spec.set_key:
        raise CatalogYamlMismatchError("metric_set_yaml_mismatch: set_key")
    db_members = registry_row.get("metric_keys_ordered")
    if db_members is not None and list(db_members) != spec.metric_keys_ordered:
        raise CatalogYamlMismatchError("metric_set_yaml_mismatch: members")


def load_and_bind(
    yaml_path: Path,
    registry_row: Mapping[str, Any],
    *,
    require_fingerprint: bool,
) -> MetricSetSpec:
    spec = load_metric_set_spec(yaml_path)
    require_yaml_matches_registry(
        spec, registry_row, require_fingerprint=require_fingerprint
    )
    return spec
