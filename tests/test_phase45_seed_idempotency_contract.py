"""Contract: Phase 4.5 metric-set seed is idempotent on re-run."""
from __future__ import annotations

from typing import Any

import pytest

from scripts.storage.seed_metric_set import apply_seed_payload_fake, apply_seed_payload_supabase
from stockradar.metrics.seed_catalog import plan_metric_set_seed
from stockradar.storage.metric_registry import FakeMetricRegistryStore

pytestmark = pytest.mark.unit

SET_KEY = "daily_core_v1__deadbeef0123"
FP_A = "a" * 64
FP_B = "b" * 64


def _payload() -> dict[str, Any]:
    return {
        "set_key": SET_KEY,
        "set_fingerprint": "c" * 64,
        "writer_workflow": "derived_writer.yml",
        "definitions": [
            {"metric_key": "alpha_metric", "display_name": "alpha_metric", "value_type": "float", "lifecycle": "active"},
            {"metric_key": "beta_metric", "display_name": "beta_metric", "value_type": "float", "lifecycle": "active"},
        ],
        "versions": [
            {
                "metric_key": "alpha_metric",
                "version_label": "v1",
                "parameters": {},
                "required_inputs": [],
                "min_history_days": 0,
                "missing_policy": {},
                "definition_canonical": {},
                "definition_fingerprint": FP_A,
                "ordinal": 0,
            },
            {
                "metric_key": "beta_metric",
                "version_label": "v1",
                "parameters": {},
                "required_inputs": [],
                "min_history_days": 0,
                "missing_policy": {},
                "definition_canonical": {},
                "definition_fingerprint": FP_B,
                "ordinal": 1,
            },
        ],
        "members": [
            {"metric_key": "alpha_metric", "definition_fingerprint": FP_A, "ordinal": 0},
            {"metric_key": "beta_metric", "definition_fingerprint": FP_B, "ordinal": 1},
        ],
    }


class _FakeResp:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}: {self._payload!r}")


class RecordingSeedClient:
    """In-memory PostgREST stand-in for seed re-run (no network)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.versions: dict[tuple[str, str], str] = {}
        self.sets: dict[str, dict[str, str]] = {}
        self.members: dict[str, list[dict[str, Any]]] = {}
        self.transitions: list[dict[str, Any]] = []

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> _FakeResp:
        self.calls.append((method, path))
        if path.endswith("/metric_definitions") and method == "POST":
            return _FakeResp([])
        if path.endswith("/metric_versions") and method == "POST":
            assert json_body is not None
            key = (str(json_body["metric_key"]), str(json_body["definition_fingerprint"]))
            vid = self.versions.setdefault(key, f"ver-{len(self.versions)}")
            return _FakeResp([{"id": vid}])
        if path.endswith("/metric_versions") and method == "GET":
            assert params is not None
            key = (
                params["metric_key"].removeprefix("eq."),
                params["definition_fingerprint"].removeprefix("eq."),
            )
            return _FakeResp([{"id": self.versions[key]}])
        if path.endswith("/metric_set_versions") and method == "GET":
            assert params is not None
            set_key = params["set_key"].removeprefix("eq.")
            row = self.sets.get(set_key)
            return _FakeResp([row] if row else [])
        if path.endswith("/metric_set_versions") and method == "POST":
            assert json_body is not None
            set_id = f"set-{len(self.sets) + 1}"
            self.sets[str(json_body["set_key"])] = {
                "id": set_id,
                "lifecycle_status": "draft",
            }
            self.members[set_id] = []
            return _FakeResp([{"id": set_id}])
        if path.endswith("/metric_set_members") and method == "GET":
            assert params is not None
            set_id = params["metric_set_version_id"].removeprefix("eq.")
            return _FakeResp(list(self.members.get(set_id, [])))
        if path.endswith("/metric_set_members") and method == "POST":
            assert json_body is not None
            set_id = str(json_body["metric_set_version_id"])
            ordinal = int(json_body["ordinal"])
            rows = self.members.setdefault(set_id, [])
            if any(int(row["ordinal"]) == ordinal for row in rows):
                return _FakeResp([])
            rows.append({"ordinal": ordinal, "metric_version_id": json_body["metric_version_id"]})
            return _FakeResp([])
        if path.endswith("/rpc/transition_metric_set") and method == "POST":
            assert json_body is not None
            set_id = str(json_body["p_set_id"])
            for row in self.sets.values():
                if row["id"] != set_id:
                    continue
                if row["lifecycle_status"] != json_body["p_from_status"]:
                    return _FakeResp({"message": "transition refused"}, status_code=400)
                row["lifecycle_status"] = str(json_body["p_to_status"])
                self.transitions.append(dict(json_body))
                return _FakeResp([])
            return _FakeResp({"message": "unknown set"}, status_code=400)
        raise AssertionError(f"unexpected request {method} {path}")


def test_plan_creates_set_and_shadows_on_first_run() -> None:
    plan = plan_metric_set_seed(
        payload=_payload(),
        existing_set=None,
        existing_member_ordinals=set(),
        target_lifecycle="shadow",
    )
    assert plan.create_set is True
    assert [member["ordinal"] for member in plan.members_to_insert] == [0, 1]
    assert plan.transition == ("draft", "shadow")
    assert plan.resulting_lifecycle == "shadow"


def test_plan_fills_missing_draft_members_then_shadows() -> None:
    plan = plan_metric_set_seed(
        payload=_payload(),
        existing_set={"id": "set-1", "lifecycle_status": "draft"},
        existing_member_ordinals={0},
        target_lifecycle="shadow",
    )
    assert plan.create_set is False
    assert [member["ordinal"] for member in plan.members_to_insert] == [1]
    assert plan.transition == ("draft", "shadow")


def test_plan_complete_shadow_is_noop() -> None:
    plan = plan_metric_set_seed(
        payload=_payload(),
        existing_set={"id": "set-1", "lifecycle_status": "shadow"},
        existing_member_ordinals={0, 1},
        target_lifecycle="shadow",
    )
    assert plan.members_to_insert == ()
    assert plan.transition is None
    assert plan.resulting_lifecycle == "shadow"


def test_plan_rejects_incomplete_non_draft_set() -> None:
    with pytest.raises(ValueError, match="members can only be inserted while draft"):
        plan_metric_set_seed(
            payload=_payload(),
            existing_set={"id": "set-1", "lifecycle_status": "shadow"},
            existing_member_ordinals={0},
            target_lifecycle="shadow",
        )


def test_fake_seed_rerun_after_set_create_fills_members_then_shadows() -> None:
    store = FakeMetricRegistryStore()
    payload = _payload()
    set_id = store.seed_set(lifecycle="draft")
    row = store.metric_set_versions[set_id]
    row["set_key"] = payload["set_key"]
    row["members"] = []
    first = apply_seed_payload_fake(store, payload, lifecycle="shadow")
    assert first.set_id == set_id
    assert first.created_set is False
    assert first.members_inserted == 2
    assert first.transition == ("draft", "shadow")
    assert row["lifecycle_status"] == "shadow"
    assert {int(member["ordinal"]) for member in row["members"]} == {0, 1}
    second = apply_seed_payload_fake(store, payload, lifecycle="shadow")
    assert second.set_id == set_id
    assert second.members_inserted == 0
    assert second.transition is None
    assert len(store.metric_set_versions) == 1
    assert len(row["members"]) == 2


def test_fake_seed_complete_rerun_is_idempotent() -> None:
    store = FakeMetricRegistryStore()
    payload = _payload()
    first = apply_seed_payload_fake(store, payload, lifecycle="shadow")
    second = apply_seed_payload_fake(store, payload, lifecycle="shadow")
    assert first.set_id == second.set_id
    assert first.created_set is True
    assert second.created_set is False
    assert second.transition is None
    row = store.metric_set_versions[first.set_id]
    assert row["lifecycle_status"] == "shadow"
    assert len(row["members"]) == 2


def test_supabase_seed_rerun_fills_missing_members_then_shadows(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RecordingSeedClient()
    client.sets[SET_KEY] = {"id": "set-1", "lifecycle_status": "draft"}
    client.members["set-1"] = [{"ordinal": 0, "metric_version_id": "ver-old"}]
    monkeypatch.setattr(
        "stockradar.storage.supabase_client.SupabaseRestAdapter.from_env",
        classmethod(lambda cls: client),
    )
    applied = apply_seed_payload_supabase(_payload(), lifecycle="shadow")
    assert applied.set_id == "set-1"
    assert applied.created_set is False
    assert applied.members_inserted == 1
    assert applied.transition == ("draft", "shadow")
    assert [row["ordinal"] for row in client.members["set-1"]] == [0, 1]
    assert client.sets[SET_KEY]["lifecycle_status"] == "shadow"
    member_posts = [path for method, path in client.calls if method == "POST" and path.endswith("/metric_set_members")]
    assert len(member_posts) == 1
    assert len(client.transitions) == 1


def test_supabase_seed_complete_shadow_does_not_retransition(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RecordingSeedClient()
    client.sets[SET_KEY] = {"id": "set-1", "lifecycle_status": "shadow"}
    client.members["set-1"] = [
        {"ordinal": 0, "metric_version_id": "ver-0"},
        {"ordinal": 1, "metric_version_id": "ver-1"},
    ]
    monkeypatch.setattr(
        "stockradar.storage.supabase_client.SupabaseRestAdapter.from_env",
        classmethod(lambda cls: client),
    )
    applied = apply_seed_payload_supabase(_payload(), lifecycle="shadow")
    assert applied.members_inserted == 0
    assert applied.transition is None
    assert applied.lifecycle == "shadow"
    assert not any(path.endswith("/metric_set_members") and method == "POST" for method, path in client.calls)
    assert client.transitions == []
    assert not any(path.endswith("/rpc/transition_metric_set") for _method, path in client.calls)
