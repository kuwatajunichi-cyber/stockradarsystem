"""Seed metric set catalog into Fake or production Supabase (ops CLI; does not activate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.metrics.registry_spec import load_metric_set_spec  # noqa: E402
from stockradar.metrics.seed_catalog import (  # noqa: E402
    SeedApplyResult,
    build_metric_set_seed_payload,
    plan_metric_set_seed,
    seed_apply_result,
)
from stockradar.storage.derived_adapters import (  # noqa: E402
    is_derived_generation_fake,
    registry_store_from_env,
)
from stockradar.storage.metric_registry import FakeMetricRegistryStore  # noqa: E402


def _find_fake_set_by_key(
    store: FakeMetricRegistryStore, set_key: str
) -> tuple[str, dict[str, Any]] | None:
    for set_id, row in store.metric_set_versions.items():
        if str(row.get("set_key") or "") == set_key:
            return set_id, row
    return None


def _overlay_fake_set_row(row: dict[str, Any], payload: dict[str, Any]) -> None:
    row["set_key"] = payload["set_key"]
    row["set_fingerprint"] = payload["set_fingerprint"]
    row["writer_workflow"] = payload["writer_workflow"]
    row["definitions"] = list(payload["definitions"])
    row["versions"] = list(payload["versions"])
    row.setdefault("members", [])


def apply_seed_payload_fake(
    store: FakeMetricRegistryStore,
    payload: dict[str, Any],
    *,
    lifecycle: str = "shadow",
) -> SeedApplyResult:
    found = _find_fake_set_by_key(store, payload["set_key"])
    existing_set = None
    existing_ordinals: set[int] = set()
    if found is not None:
        set_id, row = found
        existing_set = {"id": set_id, "lifecycle_status": str(row.get("lifecycle_status") or "")}
        existing_ordinals = {int(member["ordinal"]) for member in (row.get("members") or [])}
    plan = plan_metric_set_seed(
        payload=payload,
        existing_set=existing_set,
        existing_member_ordinals=existing_ordinals,
        target_lifecycle=lifecycle,
    )
    if plan.create_set:
        set_id = store.seed_set(lifecycle="draft")
        row = store.metric_set_versions[set_id]
        _overlay_fake_set_row(row, payload)
        row["members"] = []
    else:
        if existing_set is None:
            raise RuntimeError("seed plan expected an existing metric set")
        set_id = existing_set["id"]
        row = store.metric_set_versions[set_id]
        _overlay_fake_set_row(row, payload)
    members = list(row.get("members") or [])
    seen = {int(member["ordinal"]) for member in members}
    for member in plan.members_to_insert:
        ordinal = int(member["ordinal"])
        if ordinal not in seen:
            members.append(dict(member))
            seen.add(ordinal)
    row["members"] = members
    if plan.transition is not None:
        from_status, to_status = plan.transition
        if str(row.get("lifecycle_status") or "") != from_status:
            raise RuntimeError(
                f"transition_metric_set refused: expected {from_status}, got {row.get('lifecycle_status')}"
            )
        row["lifecycle_status"] = to_status
    return seed_apply_result(set_id, plan)


def apply_seed_payload_supabase(payload: dict[str, Any], *, lifecycle: str = "shadow") -> SeedApplyResult:
    from stockradar.storage.supabase_client import SupabaseRestAdapter

    client = SupabaseRestAdapter.from_env()
    for definition in payload["definitions"]:
        resp = client._request(
            "POST",
            "/rest/v1/metric_definitions",
            json_body=definition,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        resp.raise_for_status()
    version_ids: dict[tuple[str, str], str] = {}
    for version in payload["versions"]:
        body = {
            "metric_key": version["metric_key"],
            "version_label": version["version_label"],
            "parameters": version["parameters"],
            "required_inputs": version["required_inputs"],
            "min_history_days": version["min_history_days"],
            "missing_policy": version["missing_policy"],
            "definition_canonical": version["definition_canonical"],
            "definition_fingerprint": version["definition_fingerprint"],
        }
        resp = client._request(
            "POST",
            "/rest/v1/metric_versions",
            json_body=body,
            prefer="resolution=merge-duplicates,return=representation",
        )
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list) and rows:
            version_ids[(version["metric_key"], version["definition_fingerprint"])] = str(rows[0]["id"])
        else:
            lookup = client._request(
                "GET",
                "/rest/v1/metric_versions",
                params={
                    "metric_key": f"eq.{version['metric_key']}",
                    "definition_fingerprint": f"eq.{version['definition_fingerprint']}",
                    "select": "id",
                },
            )
            lookup.raise_for_status()
            found = lookup.json()
            version_ids[(version["metric_key"], version["definition_fingerprint"])] = str(found[0]["id"])

    existing = client._request(
        "GET",
        "/rest/v1/metric_set_versions",
        params={"set_key": f"eq.{payload['set_key']}", "select": "id,lifecycle_status"},
    )
    existing.raise_for_status()
    found_sets = existing.json()
    existing_set: dict[str, Any] | None = None
    existing_ordinals: set[int] = set()
    if isinstance(found_sets, list) and found_sets:
        existing_set = {
            "id": str(found_sets[0]["id"]),
            "lifecycle_status": str(found_sets[0]["lifecycle_status"]),
        }
        members_resp = client._request(
            "GET",
            "/rest/v1/metric_set_members",
            params={
                "metric_set_version_id": f"eq.{existing_set['id']}",
                "select": "ordinal",
            },
        )
        members_resp.raise_for_status()
        member_rows = members_resp.json()
        if isinstance(member_rows, list):
            existing_ordinals = {int(row["ordinal"]) for row in member_rows}

    plan = plan_metric_set_seed(
        payload=payload,
        existing_set=existing_set,
        existing_member_ordinals=existing_ordinals,
        target_lifecycle=lifecycle,
    )
    if plan.create_set:
        created = client._request(
            "POST",
            "/rest/v1/metric_set_versions",
            json_body={
                "set_key": payload["set_key"],
                "lifecycle_status": "draft",
                "set_fingerprint": payload["set_fingerprint"],
                "writer_workflow": payload["writer_workflow"],
            },
            prefer="return=representation",
        )
        created.raise_for_status()
        set_id = str(created.json()[0]["id"])
    else:
        if existing_set is None:
            raise RuntimeError("seed plan expected an existing metric set")
        set_id = existing_set["id"]

    for member in plan.members_to_insert:
        metric_version_id = version_ids[(member["metric_key"], member["definition_fingerprint"])]
        member_resp = client._request(
            "POST",
            "/rest/v1/metric_set_members",
            json_body={
                "metric_set_version_id": set_id,
                "metric_version_id": metric_version_id,
                "ordinal": member["ordinal"],
            },
            prefer="return=minimal",
        )
        member_resp.raise_for_status()
    if plan.transition is not None:
        from_status, to_status = plan.transition
        client._request(
            "POST",
            "/rest/v1/rpc/transition_metric_set",
            json_body={
                "p_set_id": set_id,
                "p_from_status": from_status,
                "p_to_status": to_status,
            },
        ).raise_for_status()
    return seed_apply_result(set_id, plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed metric set catalog (no activate).")
    parser.add_argument("--yaml", required=True)
    parser.add_argument("--lifecycle", choices=("draft", "shadow"), default="shadow")
    parser.add_argument("--json-output")
    args = parser.parse_args(argv)
    spec = load_metric_set_spec(args.yaml)
    payload = build_metric_set_seed_payload(spec)
    if is_derived_generation_fake():
        store = registry_store_from_env()
        if not isinstance(store, FakeMetricRegistryStore):
            store = FakeMetricRegistryStore()
        applied = apply_seed_payload_fake(store, payload, lifecycle=args.lifecycle)
    else:
        applied = apply_seed_payload_supabase(payload, lifecycle=args.lifecycle)
    result = {
        "status": "ok",
        "set_id": applied.set_id,
        "set_key": payload["set_key"],
        "set_fingerprint": payload["set_fingerprint"],
        "lifecycle": applied.lifecycle,
        "created_set": applied.created_set,
        "members_inserted": applied.members_inserted,
        "transitioned": applied.transition is not None,
        "definition_count": len(payload["definitions"]),
        "member_count": len(payload["members"]),
        "activated": False,
    }
    text = json.dumps(result, ensure_ascii=False)
    print(text)
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
