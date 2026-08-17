"""Pure metric catalog seed payload (Phase 4.5)."""
from __future__ import annotations

import re
from typing import Any

from stockradar.metrics.registry_spec import MetricSetSpec

SET_KEY_PATTERN = re.compile(r"^daily_core_v1__[a-f0-9]{12}$")


def validate_set_key(set_key: str) -> None:
    if not SET_KEY_PATTERN.match(set_key.strip()):
        raise ValueError(
            f"set_key must match daily_core_v1__{{fingerprint12}}, got {set_key!r}"
        )


def build_metric_set_seed_payload(spec: MetricSetSpec) -> dict[str, Any]:
    """Build INSERT payload for definitions / versions / set / members. Does not activate."""
    validate_set_key(spec.set_key)
    definitions: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for member in spec.members:
        if member.metric_key not in seen_keys:
            seen_keys.add(member.metric_key)
            definitions.append(
                {
                    "metric_key": member.metric_key,
                    "display_name": member.metric_key,
                    "value_type": member.value_type,
                    "lifecycle": "active",
                }
            )
        versions.append(
            {
                "metric_key": member.metric_key,
                "version_label": "v1",
                "parameters": dict(member.parameters),
                "required_inputs": list(member.required_inputs),
                "min_history_days": member.min_history_days,
                "missing_policy": dict(member.missing_policy),
                "definition_canonical": dict(member.definition_canonical),
                "definition_fingerprint": member.definition_fingerprint,
                "ordinal": member.ordinal,
            }
        )
        members.append(
            {
                "metric_key": member.metric_key,
                "definition_fingerprint": member.definition_fingerprint,
                "ordinal": member.ordinal,
            }
        )
    return {
        "set_key": spec.set_key,
        "set_family": spec.set_family,
        "set_fingerprint": spec.set_fingerprint,
        "writer_workflow": spec.writer_workflow,
        "lifecycle_status": "draft",
        "definitions": definitions,
        "versions": versions,
        "members": members,
    }
