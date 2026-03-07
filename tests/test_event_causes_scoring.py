from __future__ import annotations

from datetime import date

from stockradar.event_causes.scoring import (
    CandidateEvent,
    ScoreWeights,
    classify_cause_type,
    rank_candidates,
)


def test_rank_candidates_prefers_company_specific_tdnet_event() -> None:
    run_date = date(2026, 3, 6)
    events = [
        CandidateEvent(
            code="7203",
            source="kabutan",
            published_at="2026-03-06T12:30:00+09:00",
            title="テーマ株物色",
            raw_text_short="セクター循環",
            event_type="theme",
            event_polarity="positive",
            issuer_specificity="sector",
            novelty_level="followup",
            expected_impact_horizon="short",
            confidence_base=0.5,
            event_scope="sector",
            originality="recap",
        ),
        CandidateEvent(
            code="7203",
            source="tdnet",
            published_at="2026-03-06T08:00:00+09:00",
            title="自己株式取得",
            raw_text_short="上限を公表",
            event_type="share_buyback",
            event_polarity="positive",
            issuer_specificity="company",
            novelty_level="new",
            expected_impact_horizon="short",
            confidence_base=0.95,
            event_scope="issuer",
            originality="primary",
        ),
    ]
    ranked = rank_candidates(run_date, events, price_change_pct=3.2)
    assert len(ranked) == 2
    assert ranked[0].event.source == "tdnet"
    assert ranked[0].cause_score > ranked[1].cause_score
    assert classify_cause_type(ranked) == "A"


def test_classify_cause_type_returns_b_for_indirect_material() -> None:
    run_date = date(2026, 3, 6)
    events = [
        CandidateEvent(
            code="9999",
            source="kabutan",
            published_at="2026-03-06T10:00:00+09:00",
            title="半導体セクター上昇",
            raw_text_short="関連銘柄に物色",
            event_type="sector_news",
            event_polarity="positive",
            issuer_specificity="sector",
            novelty_level="new",
            expected_impact_horizon="short",
            confidence_base=0.8,
            event_scope="sector",
            originality="primary",
        )
    ]
    ranked = rank_candidates(run_date, events, price_change_pct=2.1)
    assert len(ranked) == 1
    assert ranked[0].cause_score >= 0.55
    assert classify_cause_type(ranked) == "B"


def test_classify_cause_type_returns_c_when_no_candidate() -> None:
    ranked = rank_candidates(date(2026, 3, 6), [], price_change_pct=0.0)
    assert ranked == []
    assert classify_cause_type(ranked) == "C"


def test_future_dated_event_gets_zero_time_proximity() -> None:
    run_date = date(2026, 3, 6)
    events = [
        CandidateEvent(
            code="7203",
            source="tdnet",
            published_at="2026-03-07T09:00:00+09:00",
            title="未来日の開示",
            raw_text_short="未来日の開示",
            event_type="earnings",
            event_polarity="neutral",
            issuer_specificity="company",
            novelty_level="new",
            expected_impact_horizon="short",
            confidence_base=0.9,
            event_scope="issuer",
            originality="primary",
        )
    ]
    ranked = rank_candidates(run_date, events, price_change_pct=None)
    assert len(ranked) == 1
    assert ranked[0].score_time_proximity == 0.0


def test_rank_candidates_v2_outputs_metadata_scores() -> None:
    run_date = date(2026, 2, 27)
    events = [
        CandidateEvent(
            code="3315",
            source="tdnet",
            published_at="2026-02-27T14:00:00+09:00",
            title="業績予想の修正に関するお知らせ",
            raw_text_short="業績予想の修正に関するお知らせ",
            event_type="earnings_revision_up",
            event_polarity="neutral",
            issuer_specificity="company",
            novelty_level="new",
            expected_impact_horizon="short",
            confidence_base=0.9,
            event_scope="issuer",
            originality="primary",
            url="https://www.release.tdnet.info/inbs/140120260226569463.pdf",
            source_category="開示",
            has_xbrl=True,
            listing_exchange="東",
            has_update_history=False,
        )
    ]
    ranked = rank_candidates(run_date, events, mode="v2")
    assert len(ranked) == 1
    top = ranked[0]
    assert top.score_source_reliability is not None
    assert top.score_disclosure_channel is not None
    assert top.score_category_signal is not None
    assert top.score_document_structure is not None
    assert top.score_name_match is not None
    assert classify_cause_type(ranked, mode="v2", decision_threshold=0.1, a_threshold=0.1) in {"A", "B"}


def test_rank_candidates_v2_name_match_boosts_score() -> None:
    run_date = date(2026, 2, 27)
    base_event = CandidateEvent(
        code="3563",
        source="kabutan",
        published_at="2026-02-27T10:22:00+09:00",
        title="Ｆ＆ＬＣが急落、中国・北京のスシローへの当局立ち入り検査報道で広報「事実確認中」",
        raw_text_short="Ｆ＆ＬＣが急落",
        event_type="other",
        event_polarity="neutral",
        issuer_specificity="company",
        novelty_level="new",
        expected_impact_horizon="short",
        confidence_base=0.7,
        event_scope="issuer",
        originality="recap",
        url="https://kabutan.jp/stock/news?code=3563&b=n202602270001",
        source_category="材料",
    )
    w = ScoreWeights(
        time_proximity=0.22,
        source_reliability=0.16,
        issuer_specificity=0.10,
        disclosure_channel=0.16,
        category_signal=0.12,
        document_structure=0.06,
        name_match=0.16,
        confidence_base=0.02,
        price_alignment=0.0,
    )
    no_alias = rank_candidates(run_date, [base_event], mode="v2", weights=w, target_name_aliases=[])
    with_alias = rank_candidates(run_date, [base_event], mode="v2", weights=w, target_name_aliases=["Ｆ＆ＬＣ"])
    assert len(no_alias) == 1 and len(with_alias) == 1
    assert (with_alias[0].score_name_match or 0.0) > (no_alias[0].score_name_match or 0.0)
    assert with_alias[0].cause_score > no_alias[0].cause_score
