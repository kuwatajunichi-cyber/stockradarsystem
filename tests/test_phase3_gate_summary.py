from __future__ import annotations

import json
from pathlib import Path

import pytest

from stockradar.storage.handoff_summary import write_producer_summary
from stockradar.storage.phase3_gate_summary import (
    cache_get_gate_lines,
    cache_put_gate_lines,
    write_cache_section,
)

pytestmark = pytest.mark.unit


def test_cache_get_gate_lines_from_json(tmp_path: Path) -> None:
    p = tmp_path / "get.json"
    p.write_text(json.dumps({"status": "ok", "cache_source": "r2"}) + "\n", encoding="utf-8")
    lines = cache_get_gate_lines(p)
    assert any("cache_source: `r2`" in line for line in lines)
    assert any("warm_cache_get_status: `ok`" in line for line in lines)


def test_cache_get_gate_lines_fallback_miss() -> None:
    lines = cache_get_gate_lines(None, fallback_cache_source="miss")
    assert any("cache_source: `miss`" in line for line in lines)


def test_cache_put_gate_lines_supabase_fields(tmp_path: Path) -> None:
    p = tmp_path / "put.json"
    p.write_text(
        json.dumps(
            {
                "status": "ok",
                "cache_source": "r2",
                "supabase_commit_ok": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines = cache_put_gate_lines(p)
    assert any("supabase_commit_ok: `True`" in line for line in lines)


def test_write_cache_section_appends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    get_json = tmp_path / "get.json"
    get_json.write_text(json.dumps({"status": "miss", "reason": "cache_pointer_missing"}) + "\n")
    write_cache_section(
        title="test gate",
        warm_cache_key="index-store-zip-v1",
        get_json=get_json,
        extra_lines=["- extra: `yes`"],
    )
    text = summary.read_text(encoding="utf-8")
    assert "## test gate" in text
    assert "warm_cache_key: `index-store-zip-v1`" in text
    assert "extra: `yes`" in text


def test_write_producer_summary_includes_supabase_commit_ok(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "cache-index-store-zip-v1.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "entry_id": "cache-index-store-zip-v1",
                "r2_put_ok": True,
                "supabase_commit_ok": True,
                "cache_source": "r2",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lines, exit_code = write_producer_summary(
        handoff_dir=handoff_dir,
        title="producer",
        required=["cache-index-store-zip-v1"],
        optional=[],
    )
    assert exit_code == 0
    joined = "\n".join(lines)
    assert "supabase_commit_ok=`True`" in joined
    assert "cache_source=`r2`" in joined
    assert "phase3_supabase_commit_ok_count: `1`" in joined
