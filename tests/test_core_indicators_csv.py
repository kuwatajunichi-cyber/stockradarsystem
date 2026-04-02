from __future__ import annotations

from pathlib import Path

from stockradar.utils.core_indicators_csv import find_latest_core_indicators_csv


def test_find_latest_excludes_event_enriched(tmp_path: Path) -> None:
    daily = tmp_path / "data" / "indicators" / "daily"
    daily.mkdir(parents=True)
    (daily / "indicators_20260110.csv").write_text("x", encoding="utf-8")
    (daily / "indicators_event_enriched_20260220.csv").write_text("y", encoding="utf-8")
    (daily / "indicators_20260201.csv").write_text("z", encoding="utf-8")

    picked = find_latest_core_indicators_csv(tmp_path)
    assert picked is not None
    assert picked.name == "indicators_20260201.csv"
