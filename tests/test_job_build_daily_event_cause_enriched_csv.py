from __future__ import annotations

from pathlib import Path

import pandas as pd

from stockradar.jobs.build_daily_event_cause_enriched_csv import main


def test_build_daily_event_cause_enriched_csv_assigns_ab_c_and_non_target(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260307.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-07", "code": "1111", "name": "A", "z_turnover_60": 3.9},
            {"date": "2026-03-07", "code": "2222", "name": "B", "z_turnover_60": 3.7},
            {"date": "2026-03-07", "code": "3333", "name": "C", "z_turnover_60": 1.2},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    summary_path = tmp_path / "data" / "analysis" / "event_causes_poc" / "event_cause_summary_20260307.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"date": "2026-03-07", "code": "1111", "cause_type": "A", "top_title": "Aニュース"},
            {"date": "2026-03-07", "code": "2222", "cause_type": "C", "top_title": ""},
        ]
    ).to_csv(summary_path, index=False, encoding="utf-8-sig")

    candidates_path = tmp_path / "data" / "analysis" / "event_causes_poc" / "event_cause_candidates_20260307.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-03-07",
                "code": "1111",
                "rank": 1,
                "cause_score": 0.9,
                "event_title": "Aニュース",
                "event_url": "https://example.com/a",
                "event_source": "tdnet",
            }
        ]
    ).to_csv(candidates_path, index=False, encoding="utf-8-sig")

    daily_cfg_path = tmp_path / "config" / "event_cause_daily.yaml"
    daily_cfg_path.parent.mkdir(parents=True, exist_ok=True)
    daily_cfg_path.write_text(
        "selection_rules:\n"
        "  any_of:\n"
        "    - type: z_turnover_gt\n"
        "      column: z_turnover_60\n"
        "      value: 3.5\n",
        encoding="utf-8",
    )

    out_path = tmp_path / "data" / "indicators" / "daily" / "indicators_event_enriched_20260307.csv"
    monkeypatch.chdir(tmp_path)
    main(
        [
            "--run-date",
            "2026-03-07",
            "--indicators",
            str(indicators_path),
            "--summary-csv",
            str(summary_path),
            "--candidates-csv",
            str(candidates_path),
            "--selection-config",
            str(daily_cfg_path),
            "--output",
            str(out_path),
        ]
    )

    out_df = pd.read_csv(out_path)

    row_a = out_df[out_df["code"] == 1111].iloc[0]
    assert row_a["event_cause_type"] == "A"
    assert row_a["event_news_1_title"] == "Aニュース"
    assert row_a["event_news_1_url"] == "https://example.com/a"

    row_c = out_df[out_df["code"] == 2222].iloc[0]
    assert row_c["event_cause_type"] == "C"
    assert row_c["event_news_1_title"] == "材料不明・需給起因疑い"
    assert (row_c["event_news_1_url"] == "") or pd.isna(row_c["event_news_1_url"])

    row_non_target = out_df[out_df["code"] == 3333].iloc[0]
    assert (row_non_target["event_cause_type"] == "") or pd.isna(row_non_target["event_cause_type"])
    assert (row_non_target["event_news_1_title"] == "") or pd.isna(row_non_target["event_news_1_title"])

