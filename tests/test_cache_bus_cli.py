"""Unit tests for cache_bus_cli with Fake Supabase + Fake R2."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def test_put_fixed_replay_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "true")
    zip_path = tmp_path / "index_store.zip"
    zip_path.write_bytes(b"zip")

    import scripts.storage.cache_bus_cli as mod

    args = mod.argparse.Namespace(
        entry_id="cache-index-store-zip-v1",
        local_path=str(zip_path),
        github_run_id="1",
        is_replay="true",
        phase3_rollout_stage="3c",
        json_output=None,
    )
    assert mod.cmd_put_fixed(args) == 0


def test_put_patched_commits_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "true")
    csv_path = tmp_path / "equity_domestic_core_with_name.csv"
    csv_path.write_text("code,name\n1,a\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"chosen_monthly_tag":"m"}', encoding="utf-8")

    import scripts.storage.cache_bus_cli as mod

    with patch.object(mod, "_r2") as mock_r2:
        mock_r2.return_value.put_object = lambda *a, **k: None
        args = mod.argparse.Namespace(
            cache_key="universe-patched-m-2026-04-10",
            monthly_tag="m",
            run_date="2026-04-10",
            csv_path=str(csv_path),
            manifest_path=str(manifest_path),
            github_run_id="99",
            source_ref="refs/heads/main",
            phase3_rollout_stage="3c",
            json_output=str(tmp_path / "out.json"),
        )
        assert mod.cmd_put_patched(args) == 0
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert payload["supabase_commit_ok"] is True
