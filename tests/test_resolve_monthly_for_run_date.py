from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from stockradar.jobs.resolve_monthly_for_run_date import resolve_monthly_tag

@pytest.mark.unit
def test_resolve_auto_uses_github_at_4a(tmp_path: Path) -> None:
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text("monthly-20260601-1\n", encoding="utf-8")
    pick, source = resolve_monthly_tag(date(2026, 6, 13), source="auto", tags_file=tags_file, phase4_stage="4a", sb_tags=[])
    assert pick.tag == "monthly-20260601-1" and source == "github"

@pytest.mark.unit
def test_resolve_auto_uses_supabase_at_4c() -> None:
    pick, source = resolve_monthly_tag(date(2026, 6, 13), source="auto", tags_file=None, phase4_stage="4c", sb_tags=["monthly-20260601-99"])
    assert pick.tag == "monthly-20260601-99" and source == "supabase"

@pytest.mark.unit
def test_resolve_auto_4b_falls_back_to_github_when_supabase_not_eligible(tmp_path: Path) -> None:
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text("monthly-20260207-1\nmonthly-20260101-1\n", encoding="utf-8")
    pick, source = resolve_monthly_tag(
        date(2026, 6, 13),
        source="auto",
        tags_file=tags_file,
        phase4_stage="4b",
        sb_tags=["monthly-20260701-99"],
    )
    assert pick.universe_resolution == "time_series_ok"
    assert pick.tag == "monthly-20260207-1"
    assert source == "github_fallback"

@pytest.mark.unit
def test_resolve_auto_4b_keeps_supabase_when_github_is_fallback_latest(tmp_path: Path) -> None:
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text("monthly-20260201-1\n", encoding="utf-8")
    pick, source = resolve_monthly_tag(
        date(2026, 1, 15),
        source="auto",
        tags_file=tags_file,
        phase4_stage="4b",
        sb_tags=["monthly-20260101-1"],
    )
    assert pick.universe_resolution == "time_series_ok"
    assert pick.tag == "monthly-20260101-1"
    assert source == "supabase"
