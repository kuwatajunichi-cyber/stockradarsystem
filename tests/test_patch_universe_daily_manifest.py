"""patch_universe_daily manifest fields (no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stockradar.jobs import patch_universe_daily as mod


def test_manifest_records_chosen_tag_and_resolution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "fetch_delisted_codes", lambda *a, **k: set())

    inp = tmp_path / "core.csv"
    pd.DataFrame({"code": ["7203"], "name": ["Toyota"]}).to_csv(inp, index=False)

    mod.main(
        [
            "--input",
            str(inp),
            "--run-date",
            "2026-02-11",
            "--base-release",
            "monthly-20260207-999",
            "--chosen-monthly-tag",
            "monthly-20260207-999",
            "--universe-resolution",
            "fallback_latest",
            "--resolution-reason",
            "audit test",
        ]
    )

    manifest_path = tmp_path / "data" / "universe" / "jpx" / "patched_cache" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["chosen_monthly_tag"] == "monthly-20260207-999"
    assert payload["universe_resolution"] == "fallback_latest"
    assert payload["reason"] == "audit test"
    assert payload["base_release"] == "monthly-20260207-999"
    assert payload["base_release_date"] == "2026-02-07"