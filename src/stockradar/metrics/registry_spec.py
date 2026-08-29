"""Metric set catalog loader and validation (Phase 4.5)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from stockradar.metrics.fingerprint import (
    compute_definition_fingerprint,
    compute_set_fingerprint,
    short_fingerprint12,
)


@dataclass(frozen=True)
class MetricMemberSpec:
    metric_key: str
    value_type: str
    min_history_days: int
    parameters: dict[str, Any]
    required_inputs: list[str]
    missing_policy: dict[str, Any]
    definition_canonical: dict[str, Any]
    definition_fingerprint: str
    ordinal: int
    seed_capability: str | None = None
    required_benchmarks: tuple[str, ...] = ()
    lookback_trading_days: int | None = None
    warmup_trading_days: int | None = None
    listing_source_policy: str | None = None


@dataclass(frozen=True)
class MetricSetSpec:
    path: Path
    set_family: str
    writer_workflow: str
    version_parameters: dict[str, Any]
    members: tuple[MetricMemberSpec, ...]

    @property
    def metric_keys_ordered(self) -> list[str]:
        return [m.metric_key for m in self.members]

    @property
    def set_fingerprint(self) -> str:
        member_payload = [
            {
                "metric_key": m.metric_key,
                "definition_fingerprint": m.definition_fingerprint,
                "ordinal": m.ordinal,
            }
            for m in self.members
        ]
        return compute_set_fingerprint(members=member_payload, set_family=self.set_family)

    @property
    def set_key(self) -> str:
        return f"{self.set_family}__{short_fingerprint12(self.set_fingerprint)}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_metric_set_v1_path() -> Path:
    return _repo_root() / "config" / "metrics" / "metric_set_v1.yaml"


def default_metric_set_v1_free_path() -> Path:
    return _repo_root() / "config" / "metrics" / "metric_set_v1_free.yaml"


def definition_payload_for_fingerprint(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item["definition_canonical"])
    payload["required_inputs"] = list(item.get("required_inputs") or [])
    payload["missing_policy"] = dict(item.get("missing_policy") or {})
    return payload


def load_metric_set_spec(path: Path | str | None = None) -> MetricSetSpec:
    yaml_path = Path(path) if path is not None else default_metric_set_v1_path()
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid metric set YAML: {yaml_path}")
    set_family = str(raw.get("set_family") or "")
    writer_workflow = str(raw.get("writer_workflow") or "derived_writer")
    version_parameters = dict(raw.get("version_parameters") or {})
    members_raw = raw.get("members")
    if not isinstance(members_raw, list) or not members_raw:
        raise ValueError(f"members required: {yaml_path}")
    members: list[MetricMemberSpec] = []
    for idx, item in enumerate(members_raw):
        if not isinstance(item, dict):
            raise ValueError(f"member {idx} must be mapping")
        fp = str(item["definition_fingerprint"])
        expected_fp = compute_definition_fingerprint(definition_payload_for_fingerprint(item))
        if fp != expected_fp:
            raise ValueError(
                f"definition_fingerprint mismatch for {item['metric_key']}: {fp} != {expected_fp}"
            )
        members.append(
            MetricMemberSpec(
                metric_key=str(item["metric_key"]),
                value_type=str(item["value_type"]),
                min_history_days=int(item["min_history_days"]),
                parameters=dict(item.get("parameters") or {}),
                required_inputs=list(item.get("required_inputs") or []),
                missing_policy=dict(item.get("missing_policy") or {}),
                definition_canonical=dict(item["definition_canonical"]),
                definition_fingerprint=str(item["definition_fingerprint"]),
                ordinal=int(item.get("ordinal", idx)),
                seed_capability=(
                    str(item["seed_capability"]).strip()
                    if item.get("seed_capability") is not None
                    else None
                ),
                required_benchmarks=tuple(
                    str(x) for x in (item.get("required_benchmarks") or [])
                ),
                lookback_trading_days=(
                    int(item["lookback_trading_days"])
                    if item.get("lookback_trading_days") is not None
                    else None
                ),
                warmup_trading_days=(
                    int(item["warmup_trading_days"])
                    if item.get("warmup_trading_days") is not None
                    else None
                ),
                listing_source_policy=(
                    str(item["listing_source_policy"]).strip()
                    if item.get("listing_source_policy") is not None
                    else None
                ),
            )
        )
    members_sorted = tuple(sorted(members, key=lambda m: m.ordinal))
    return MetricSetSpec(
        path=yaml_path,
        set_family=set_family,
        writer_workflow=writer_workflow,
        version_parameters=version_parameters,
        members=members_sorted,
    )


def validate_version_parameters(
    *,
    spec: MetricSetSpec,
    rs_windows: list[int] | None = None,
    rs_benchmark: str | None = None,
    z_lookback_days: int | None = None,
) -> None:
    params = spec.version_parameters
    expected_windows = list(params.get("rs_windows") or [])
    expected_benchmark = str(params.get("rs_benchmark") or "")
    expected_z = int(params.get("z_lookback_days") or 0)
    if rs_windows is not None and list(rs_windows) != expected_windows:
        raise ValueError(
            f"rs_windows mismatch: got {rs_windows}, catalog expects {expected_windows}"
        )
    if rs_benchmark is not None and str(rs_benchmark) != expected_benchmark:
        raise ValueError(
            f"rs_benchmark mismatch: got {rs_benchmark}, catalog expects {expected_benchmark}"
        )
    if z_lookback_days is not None and int(z_lookback_days) != expected_z:
        raise ValueError(
            f"z_lookback_days mismatch: got {z_lookback_days}, catalog expects {expected_z}"
        )


_SEED_CAPABILITIES = frozenset(
    {"instrument_local", "benchmark_relative", "not_series_seedable"}
)


def require_seed_metric_input_contract(spec: MetricSetSpec) -> None:
    """Fail closed when ADR-005 §3.1 seed fields are missing (not fingerprint)."""
    for m in spec.members:
        if not m.seed_capability or m.seed_capability not in _SEED_CAPABILITIES:
            raise ValueError(f"metric_input_contract_missing: seed_capability for {m.metric_key}")
        if m.listing_source_policy not in (None, "first_valid_bar"):
            raise ValueError(
                f"metric_input_contract_missing: listing_source_policy for {m.metric_key}"
            )
        if m.lookback_trading_days is None:
            raise ValueError(f"metric_input_contract_missing: lookback_trading_days for {m.metric_key}")
        if m.seed_capability == "benchmark_relative" and not m.required_benchmarks:
            raise ValueError(
                f"metric_input_contract_missing: required_benchmarks for {m.metric_key}"
            )


def metric_set_is_series_seedable(spec: MetricSetSpec) -> bool:
    return all(m.seed_capability != "not_series_seedable" for m in spec.members)
