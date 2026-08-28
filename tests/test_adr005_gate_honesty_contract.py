"""Contract: ADR-005 gate SSOT must stay proposed until live evidence exists."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_GATE_STATUS = _REPO / "docs" / "operations" / "adr005_gate_status.yaml"
_ROADMAP = _REPO / "docs" / "operations" / "issue_93_roadmap.md"
_INDEX = _REPO / "docs" / "INDEX.md"
_CRON = _REPO / "docs" / "contracts" / "monthly_new_core_backfill_cloudflare_cron_dispatch.md"
_RUNBOOK = _REPO / "docs" / "contracts" / "monthly_new_core_backfill.md"
_REQUIRED_PR_GATES = (
    "pr-005-docs-adoption",
    "pr-005-daily-cas",
    "pr-005-monthly-rpc",
    "pr-005-series-seed",
)


def _load_gate_status() -> dict:
    raw = _GATE_STATUS.read_bytes()
    assert raw.count(b"\x00") == 0, "adr005_gate_status.yaml must be UTF-8 without NULs"
    assert not raw.startswith(b"\xef\xbb\xbf")
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("adr005_gate_status.yaml must be a mapping")
    return data


@pytest.mark.unit
def test_adr005_gate_status_stays_proposed_and_owned() -> None:
    data = _load_gate_status()
    assert data.get("overall_status") == "proposed"
    owner = str(data.get("owner") or "").strip()
    assert owner, "owner must not be empty"
    repair = str(data.get("repair_approver_team") or "").strip()
    assert repair, "repair_approver_team must not be empty"
    live = data.get("live_gate_005")
    assert isinstance(live, dict)
    assert live.get("status") == "open"
    impl = data.get("implementation_snapshot")
    assert isinstance(impl, dict)
    assert impl.get("code_unstarted") is True
    assert impl.get("workflows_unstarted") is True
    pr_gates = data.get("pr_gates")
    assert isinstance(pr_gates, dict)
    for gate_id in _REQUIRED_PR_GATES:
        gate = pr_gates.get(gate_id)
        assert isinstance(gate, dict), f"missing pr_gate {gate_id}"
        status = gate.get("status")
        assert status in {"pending", "local_only"}, f"{gate_id} status {status!r} is not an open docs/impl gate"
        assert not gate.get("merge_commit"), f"{gate_id} must not claim merge without evidence"


@pytest.mark.unit
def test_adr005_docs_index_and_roadmap_stay_proposed() -> None:
    index = _INDEX.read_text(encoding="utf-8")
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    assert "adr-005-monthly-new-core-backfill.md" in index
    assert "adr005_gate_status.yaml" in index
    assert "Proposed" in index
    assert "adr-005-monthly-new-core-backfill.md" in roadmap
    assert "Proposed" in roadmap
    assert "未採択" in roadmap or "未実装" in roadmap
    assert "PR-45-1..4 merged・rollout 4.5c・Path B active・live_gate open（Path B soak 未達）・capacity_gate closed" in roadmap


@pytest.mark.unit
def test_adr005_cron_skeleton_exists_utf8_without_bom() -> None:
    raw = _CRON.read_bytes()
    assert raw.count(b"\x00") == 0
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "*/15 * * * *" in text
    assert "MNC_DISPATCH_ENABLED" in text
    assert "contents: read" in text
    assert "GITHUB_TOKEN" in text
    assert "actions: write" in text
    assert "wrangler.toml" in text
    assert "Liveness (required)" in text
    raw_rb = _RUNBOOK.read_bytes()
    assert raw_rb.count(b"\x00") == 0
    assert not raw_rb.startswith(b"\xef\xbb\xbf")
    rb = raw_rb.decode("utf-8")
    assert "partition_index" in rb
    assert "pr-005-daily-cas" in rb
