"""Pure metric catalog seed payload (Phase 4.5)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from stockradar.metrics.registry_spec import MetricSetSpec

SET_KEY_PATTERN = re.compile(r"^daily_core_v1__[a-f0-9]{12}$")
_ALLOWED_SEED_LIFECYCLES = frozenset({"draft", "shadow"})


@dataclass(frozen=True)
class SeedApplyPlan:
    """Idempotent seed completion: create set, fill missing members, maybe draft→shadow."""

    create_set: bool
    members_to_insert: tuple[dict[str, Any], ...]
    transition: tuple[str, str] | None
    current_lifecycle: str

    @property
    def resulting_lifecycle(self) -> str:
        if self.transition is not None:
            return self.transition[1]
        return self.current_lifecycle


@dataclass(frozen=True)
class SeedApplyResult:
    set_id: str
    created_set: bool
    members_inserted: int
    transition: tuple[str, str] | None
    lifecycle: str


def seed_apply_result(set_id: str, plan: SeedApplyPlan) -> SeedApplyResult:
    return SeedApplyResult(
        set_id=set_id,
        created_set=plan.create_set,
        members_inserted=len(plan.members_to_insert),
        transition=plan.transition,
        lifecycle=plan.resulting_lifecycle,
    )


def plan_metric_set_seed(
    *,
    payload: dict[str, Any],
    existing_set: dict[str, Any] | None,
    existing_member_ordinals: set[int],
    target_lifecycle: str,
) -> SeedApplyPlan:
    """Plan catalog seed so re-runs fill missing draft members and do not re-transition.

    Members may be inserted only while the set is draft (Postgres trigger). A non-draft
    set with missing ordinals is a hard error, not a silent shadow promotion.
    """
    if target_lifecycle not in _ALLOWED_SEED_LIFECYCLES:
        raise ValueError("seed CLI may only create draft or shadow; activation is ops CAS")
    desired_members = list(payload.get("members") or [])
    if existing_set is None:
        return SeedApplyPlan(
            create_set=True,
            members_to_insert=tuple(desired_members),
            transition=("draft", "shadow") if target_lifecycle == "shadow" else None,
            current_lifecycle="draft",
        )
    current = str(existing_set.get("lifecycle_status") or "").strip().lower()
    missing = tuple(
        member
        for member in desired_members
        if int(member["ordinal"]) not in existing_member_ordinals
    )
    if missing and current != "draft":
        set_id = existing_set.get("id")
        raise ValueError(
            f"metric set {set_id} is {current} with missing member ordinals; "
            "members can only be inserted while draft"
        )
    transition: tuple[str, str] | None = None
    if target_lifecycle == "shadow" and current == "draft":
        transition = ("draft", "shadow")
    return SeedApplyPlan(
        create_set=False,
        members_to_insert=missing,
        transition=transition,
        current_lifecycle=current,
    )


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
