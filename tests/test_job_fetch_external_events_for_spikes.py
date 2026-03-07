from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.jobs.fetch_external_events_for_spikes import main
from stockradar.sources.external_events import ScrapedEvent


def test_fetch_external_events_for_spikes_outputs_jsonl(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.8},
            {"date": "2026-03-06", "code": "6758", "name": "Sony", "z_turnover_60": 3.2},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        if code != "7203":
            return []
        return [
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at="2026-03-06T10:00:00",
                title="自己株式の取得に関するお知らせ",
                raw_text_short="自己株式の取得に関するお知らせ",
                event_type="share_buyback",
                event_polarity="positive",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=7203&b=n202603060001",
            )
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        if target_day.isoformat() != "2026-03-06":
            return []
        return [
            ScrapedEvent(
                code="7203",
                source="tdnet",
                published_at="2026-03-06T16:30:00",
                title="自己株式取得に係る事項の変更等に関するお知らせ",
                raw_text_short="自己株式取得に係る事項の変更等に関するお知らせ",
                event_type="share_buyback",
                event_polarity="positive",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.9,
                event_scope="issuer",
                originality="primary",
                url="https://www.release.tdnet.info/inbs/140120260306577638.pdf",
            )
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--z-threshold",
            "4.0",
            "--lookback-days",
            "5",
            "--output",
            str(output_path),
        ]
    )

    assert output_path.exists()
    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 2
    assert all(r["code"] == "7203" for r in rows)
    assert {r["source"] for r in rows} == {"kabutan", "tdnet"}
    assert all("source_category" in r for r in rows)


def test_fetch_external_events_for_spikes_respects_cutoff_time(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame([{"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.8}]).to_csv(
        indicators_path, index=False, encoding="utf-8-sig"
    )

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        return [
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at="2026-03-06T15:20:00",
                title="場中ニュース",
                raw_text_short="場中ニュース",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=7203&b=n202603060001",
            ),
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at="2026-03-06T16:00:00",
                title="引け後ニュース",
                raw_text_short="引け後ニュース",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=7203&b=n202603060002",
            ),
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--z-threshold",
            "3.5",
            "--lookback-days",
            "1",
            "--cutoff-time",
            "15:30",
            "--output",
            str(output_path),
        ]
    )

    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["title"] == "場中ニュース"


def test_fetch_external_events_for_spikes_excludes_kabutan_categories(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame([{"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.2}]).to_csv(
        indicators_path, index=False, encoding="utf-8-sig"
    )

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        return [
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at="2026-03-06T10:00:00",
                title="特集記事",
                raw_text_short="特集記事",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="low",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="market",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=7203&b=n1",
                source_category="特集",
            ),
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at="2026-03-06T10:10:00",
                title="材料記事",
                raw_text_short="材料記事",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=7203&b=n2",
                source_category="材料",
            ),
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--z-threshold",
            "3.5",
            "--lookback-days",
            "1",
            "--exclude-kabutan-categories",
            "特集,注目",
            "--output",
            str(output_path),
        ]
    )
    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["title"] == "材料記事"


def test_fetch_external_events_for_spikes_prefers_tdnet_when_duplicate(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame([{"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.2}]).to_csv(
        indicators_path, index=False, encoding="utf-8-sig"
    )

    dup_title = "自己株式取得に係る事項の決定に関するお知らせ"
    dup_dt = "2026-03-06T15:00:00"

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        return [
            ScrapedEvent(
                code="7203",
                source="kabutan",
                published_at=dup_dt,
                title=dup_title,
                raw_text_short=dup_title,
                event_type="share_buyback",
                event_polarity="positive",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/disclosures/pdf/1/",
                source_category="開示",
            )
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        return [
            ScrapedEvent(
                code="7203",
                source="tdnet",
                published_at=dup_dt,
                title=dup_title,
                raw_text_short=dup_title,
                event_type="share_buyback",
                event_polarity="positive",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.9,
                event_scope="issuer",
                originality="primary",
                url="https://www.release.tdnet.info/inbs/1.pdf",
            )
        ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--z-threshold",
            "3.5",
            "--lookback-days",
            "1",
            "--output",
            str(output_path),
        ]
    )
    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["source"] == "tdnet"


def test_fetch_external_events_for_spikes_selection_rules_z_turnover_lt(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 4.2},
            {"date": "2026-03-06", "code": "6758", "name": "Sony", "z_turnover_60": -3.8},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    cfg_path = tmp_path / "config" / "event_cause_daily.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "selection_rules:\n"
        "  any_of:\n"
        "    - type: z_turnover_lt\n"
        "      column: z_turnover_60\n"
        "      value: -3.5\n",
        encoding="utf-8",
    )

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        if code != "6758":
            return []
        return [
            ScrapedEvent(
                code="6758",
                source="kabutan",
                published_at="2026-03-06T10:00:00",
                title="需給ニュース",
                raw_text_short="需給ニュース",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=6758&b=n1",
            )
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--selection-config",
            str(cfg_path),
            "--output",
            str(output_path),
        ]
    )

    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["code"] == "6758"


def test_fetch_external_events_for_spikes_selection_rules_candle_labels(tmp_path: Path, monkeypatch) -> None:
    indicators_dir = tmp_path / "data" / "indicators" / "daily"
    indicators_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = indicators_dir / "indicators_20260306.csv"
    pd.DataFrame(
        [
            {"date": "2026-03-06", "code": "7203", "name": "Toyota", "z_turnover_60": 0.2, "candle_labels": "DIR_BULL"},
            {"date": "2026-03-06", "code": "6758", "name": "Sony", "z_turnover_60": 0.1, "candle_labels": "LIMIT_HIGH_TOUCH,DIR_BULL"},
        ]
    ).to_csv(indicators_path, index=False, encoding="utf-8-sig")

    cfg_path = tmp_path / "config" / "event_cause_daily.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "selection_rules:\n"
        "  any_of:\n"
        "    - type: candle_labels_contains_any\n"
        "      column: candle_labels\n"
        "      values: [\"LIMIT_HIGH\", \"LIMIT_LOW\"]\n",
        encoding="utf-8",
    )

    def _fake_kabutan(code: str, **kwargs):  # noqa: ANN001
        if code != "6758":
            return []
        return [
            ScrapedEvent(
                code="6758",
                source="kabutan",
                published_at="2026-03-06T10:00:00",
                title="制限値幅タッチ疑い",
                raw_text_short="制限値幅タッチ疑い",
                event_type="other",
                event_polarity="neutral",
                issuer_specificity="company",
                novelty_level="new",
                expected_impact_horizon="short",
                confidence_base=0.7,
                event_scope="issuer",
                originality="recap",
                url="https://kabutan.jp/stock/news?code=6758&b=n1",
            )
        ]

    def _fake_tdnet(target_day: date, **kwargs):  # noqa: ANN001
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_kabutan_news_for_month", _fake_kabutan)
    monkeypatch.setattr("stockradar.jobs.fetch_external_events_for_spikes.fetch_tdnet_disclosures_for_date", _fake_tdnet)

    output_path = tmp_path / "data" / "external" / "events" / "news_tdnet_events.jsonl"
    main(
        [
            "--run-date",
            "2026-03-06",
            "--indicators",
            str(indicators_path),
            "--selection-config",
            str(cfg_path),
            "--output",
            str(output_path),
        ]
    )

    rows = [json.loads(x) for x in output_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["code"] == "6758"
