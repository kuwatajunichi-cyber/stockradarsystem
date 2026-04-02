from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stockradar.jobs.rank_turnover_event_causes import main


def test_rank_turnover_event_causes_job_outputs_files(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.6, "price_change_pct": 2.5},
            {"date": "2026-03-06", "code": "6758", "name": "Sony", "z_turnover_60": 3.1, "price_change_pct": 1.2},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    events_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "code": "7203",
        "source": "tdnet",
        "published_at": "2026-03-06T08:00:00+09:00",
        "title": "自己株式取得",
        "raw_text_short": "上限決定",
        "event_type": "share_buyback",
        "event_polarity": "positive",
        "issuer_specificity": "company",
        "novelty_level": "new",
        "expected_impact_horizon": "short",
        "confidence_base": 0.95,
        "event_scope": "issuer",
        "originality": "primary",
    }
    with events_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    cfg_path = tmp_path / "config" / "event_cause_poc.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "weights:\n"
        "  time_proximity: 0.24\n"
        "  issuer_specificity: 0.20\n"
        "  material_strength: 0.20\n"
        "  primary_source: 0.12\n"
        "  novelty: 0.12\n"
        "  price_alignment: 0.08\n"
        "  confidence_base: 0.04\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--events-jsonl",
            str(events_path),
            "--config",
            str(cfg_path),
            "--z-threshold",
            "4.0",
        ]
    )

    out_summary = tmp_path / "data" / "analysis" / "event_causes_poc" / "event_cause_summary_20260306.csv"
    out_detail = tmp_path / "data" / "analysis" / "event_causes_poc" / "event_cause_candidates_20260306.csv"
    assert out_summary.exists()
    assert out_detail.exists()

    summary_df = pd.read_csv(out_summary)
    assert len(summary_df) == 1
    assert summary_df.loc[0, "code"] == 7203 or str(summary_df.loc[0, "code"]) == "7203"
    assert summary_df.loc[0, "cause_type"] == "A"
    assert summary_df.loc[0, "ohlc_as_of"] == "2026-03-06"


def test_rank_turnover_event_causes_respects_selection_rules(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.6, "price_change_pct": 2.5},
            {"date": "2026-03-06", "code": "6758", "name": "Sony", "z_turnover_60": -3.8, "price_change_pct": -1.2},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    events_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "code": "6758",
        "source": "tdnet",
        "published_at": "2026-03-06T08:00:00+09:00",
        "title": "需給改善に関するお知らせ",
        "raw_text_short": "需給改善に関するお知らせ",
        "event_type": "other",
        "event_polarity": "neutral",
        "issuer_specificity": "company",
        "novelty_level": "new",
        "expected_impact_horizon": "short",
        "confidence_base": 0.95,
        "event_scope": "issuer",
        "originality": "primary",
    }
    with events_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    cfg_path = tmp_path / "config" / "event_cause_poc.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "weights:\n"
        "  time_proximity: 0.24\n"
        "  issuer_specificity: 0.20\n"
        "  material_strength: 0.20\n"
        "  primary_source: 0.12\n"
        "  novelty: 0.12\n"
        "  price_alignment: 0.08\n"
        "  confidence_base: 0.04\n",
        encoding="utf-8",
    )
    daily_cfg_path = tmp_path / "config" / "event_cause_daily.yaml"
    daily_cfg_path.write_text(
        "selection_rules:\n"
        "  any_of:\n"
        "    - type: z_turnover_lt\n"
        "      column: z_turnover_60\n"
        "      value: -3.5\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--events-jsonl",
            str(events_path),
            "--config",
            str(cfg_path),
            "--selection-config",
            str(daily_cfg_path),
        ]
    )

    out_summary = tmp_path / "data" / "analysis" / "event_causes_poc" / "event_cause_summary_20260306.csv"
    summary_df = pd.read_csv(out_summary)
    assert len(summary_df) == 1
    assert str(summary_df.loc[0, "code"]) == "6758"
