"""Contract: ADR-005 gate SSOT after docs adoption (in_progress, live_gate_005 open)."""
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
_PHASE45_PHRASE = (
    "PR-45-1..4 merged・rollout 4.5c・Path B active・"
    "live_gate closed (user-authorized waiver 2026-08-29)・capacity_gate closed"
)
_REQUIRED_PR_GATES = (
    "pr-005-docs-adoption",
    "pr-005-daily-cas",
    "pr-005-monthly-rpc",
    "pr-005-series-seed",
)
_MERGE_SHA = "9c58ddc6073779f9f97311f35fe13ace47d7fb29"


def _load_gate_status() -> dict:
    raw = _GATE_STATUS.read_bytes()
    assert raw.count(b"\x00") == 0, "adr005_gate_status.yaml must be UTF-8 without NULs"
    assert not raw.startswith(b"\xef\xbb\xbf")
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("adr005_gate_status.yaml must be a mapping")
    return data


@pytest.mark.unit
def test_adr005_gate_status_in_progress_and_owned() -> None:
    data = _load_gate_status()
    assert data.get("overall_status") == "in_progress"
    owner = str(data.get("owner") or "").strip()
    assert owner, "owner must not be empty"
    repair = str(data.get("repair_approver_team") or "").strip()
    assert repair, "repair_approver_team must not be empty"
    live = data.get("live_gate_005")
    assert isinstance(live, dict)
    assert live.get("status") == "open"
    impl = data.get("implementation_snapshot")
    assert isinstance(impl, dict)
    assert impl.get("code_unstarted") is False
    assert impl.get("workflows_unstarted") is False
    pr_gates = data.get("pr_gates")
    assert isinstance(pr_gates, dict)
    for gate_id in _REQUIRED_PR_GATES:
        gate = pr_gates.get(gate_id)
        assert isinstance(gate, dict), f"missing pr_gate {gate_id}"
        status = gate.get("status")
        assert status in {"pending", "local_only", "merged_and_verified"}, (
            f"{gate_id} status {status!r}"
        )
        if status == "merged_and_verified":
            assert gate.get("merge_commit"), f"{gate_id} needs merge_commit"
            assert gate.get("merge_ci_run_url"), f"{gate_id} needs merge_ci_run_url"
        else:
            assert not gate.get("merge_commit"), f"{gate_id} must not claim merge without evidence"


@pytest.mark.unit
def test_adr005_pr_gates_merged_after_pr159() -> None:
    data = _load_gate_status()
    pr_gates = data.get("pr_gates")
    assert isinstance(pr_gates, dict)
    for gate_id in _REQUIRED_PR_GATES:
        gate = pr_gates[gate_id]
        assert gate.get("status") == "merged_and_verified"
        assert str(gate.get("merge_commit")) == _MERGE_SHA
        assert "33235945903" in str(gate.get("merge_ci_run_url") or "")


@pytest.mark.unit
def test_adr005_docs_index_and_roadmap_adopted() -> None:
    index = _INDEX.read_text(encoding="utf-8")
    roadmap = _ROADMAP.read_text(encoding="utf-8")
    assert "adr-005-monthly-new-core-backfill.md" in index
    assert "adr005_gate_status.yaml" in index
    assert "Adopted" in index
    assert "adr-005-monthly-new-core-backfill.md" in roadmap
    assert "Adopted" in roadmap
    assert _PHASE45_PHRASE in roadmap
    assert "未達" not in roadmap.split("## Phase 5")[0]
    assert "PR #159" in roadmap or "9c58ddc" in roadmap or "merged" in roadmap.lower()


@pytest.mark.unit
def test_adr005_cron_skeleton_exists_utf8_without_bom() -> None:
    raw = _CRON.read_bytes()
    assert raw.count(b"\x00") == 0
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "*/15 2-5 1 * *" in text
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


@pytest.mark.unit
def test_adr005_companion_docs_match_waiver_close() -> None:
    """Adoption sync: ADR-004 / daily_replay / cutover must not claim live_gate open or ADR-005 unadopted."""
    adr004 = (_REPO / "docs" / "adr" / "adr-004-derived-indicators-warm-cache.md").read_text(encoding="utf-8")
    assert "live_gate_45c` closed" in adr004 or "live_gate_45c closed" in adr004
    assert "Proposed amendment。未採択。未実装。" not in adr004
    assert "Adopted" in adr004
    assert "（Proposed。series_seed" not in adr004
    replay = (_REPO / "docs" / "contracts" / "daily_replay_and_monthly_universe.md").read_text(encoding="utf-8")
    assert "soak 未達のため open" not in replay
    assert "Proposed。未実装。" not in replay
    cutover = (_REPO / "docs" / "operations" / "phase4_5_cutover.md").read_text(encoding="utf-8")
    assert "live_gate_45c closed" in cutover
    assert "soak 未達のため open" not in cutover
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    assert "Implementation is unstarted" not in runbook
    assert "fixed-key until" not in runbook
    schema = (_REPO / "docs" / "contracts" / "supabase_control_plane_schema.md").read_text(encoding="utf-8")
    assert "fixed-key until pr-005-daily-cas" not in schema
    adr005 = (_REPO / "docs" / "adr" / "adr-005-monthly-new-core-backfill.md").read_text(encoding="utf-8")
    assert "live の `target_r2_key_pattern` は fixed-key のまま" not in adr005
    assert "それまで live は固定 key" not in adr005
    assert "本 docs PR では変えない" not in adr005
    mapping_doc = (_REPO / "docs" / "contracts" / "github_state_to_r2_supabase_mapping.md").read_text(
        encoding="utf-8"
    )
    assert "proposed` until live writer exists" not in mapping_doc
    assert "live fixed `target_r2_key_pattern`" not in mapping_doc
    gate45 = yaml.safe_load(
        (_REPO / "docs" / "operations" / "phase4_5_gate_status.yaml").read_text(encoding="utf-8")
    )
    assert gate45.get("overall_status") == "closed"
    snap = gate45.get("implementation_snapshot") or {}
    assert isinstance(snap.get("local_worktree_has_unmerged_changes"), bool)
