"""
売買代金急増の背景候補を順位付けするPoCロジック。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
import unicodedata


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class CandidateEvent:
    code: str
    source: str
    published_at: str
    title: str
    raw_text_short: str
    event_type: str
    event_polarity: str
    issuer_specificity: str
    novelty_level: str
    expected_impact_horizon: str
    confidence_base: float = 0.5
    event_scope: str = ""
    originality: str = ""
    url: str = ""
    source_category: str = ""
    has_xbrl: bool | None = None
    listing_exchange: str = ""
    has_update_history: bool | None = None


@dataclass(frozen=True)
class ScoreWeights:
    time_proximity: float = 0.24
    issuer_specificity: float = 0.20
    material_strength: float = 0.20
    primary_source: float = 0.12
    novelty: float = 0.12
    price_alignment: float = 0.08
    confidence_base: float = 0.04
    source_reliability: float = 0.0
    disclosure_channel: float = 0.0
    category_signal: float = 0.0
    document_structure: float = 0.0
    name_match: float = 0.0


@dataclass(frozen=True)
class RankedCandidate:
    event: CandidateEvent
    cause_score: float
    score_time_proximity: float
    score_issuer_specificity: float
    score_material_strength: float
    score_primary_source: float
    score_novelty: float
    score_price_alignment: float
    score_confidence_base: float
    score_source_reliability: float | None = None
    score_disclosure_channel: float | None = None
    score_category_signal: float | None = None
    score_document_structure: float | None = None
    score_name_match: float | None = None


def _score_time_proximity(run_date: date, published_at: str) -> float:
    dt = _parse_dt(published_at)
    if dt is None:
        return 0.1
    days = (run_date - dt.date()).days
    if days < 0:
        return 0.0
    if days == 0:
        return 1.0
    if days == 1:
        return 0.9
    if days <= 5:
        return 0.6
    if days <= 20:
        return 0.35
    return 0.1


def _score_issuer_specificity(value: str, scope: str) -> float:
    v = value.strip().lower()
    s = scope.strip().lower()
    mapping = {
        "company": 1.0,
        "issuer": 1.0,
        "high": 0.9,
        "sector": 0.55,
        "medium": 0.55,
        "theme": 0.45,
        "market": 0.2,
        "macro": 0.2,
        "low": 0.2,
    }
    if v in mapping:
        return mapping[v]
    if s in mapping:
        return mapping[s]
    return 0.4


def _score_material_strength(event_type: str) -> float:
    key = event_type.strip().lower()
    high = {
        "earnings_revision_up",
        "earnings",
        "share_buyback",
        "tob",
        "mna",
        "partnership",
        "large_order",
        "guidance_raise",
    }
    medium = {
        "monthly",
        "new_product",
        "analyst_rating",
        "theme",
        "sector_news",
    }
    low = {
        "market_news",
        "ranking",
        "price_commentary",
        "supply_demand_commentary",
    }
    if key in high:
        return 0.95
    if key in medium:
        return 0.65
    if key in low:
        return 0.25
    return 0.45


def _score_primary_source(source: str, originality: str) -> float:
    src = source.strip().lower()
    org = originality.strip().lower()
    base = 0.55
    if src == "tdnet":
        base = 1.0
    elif src == "kabutan":
        base = 0.72
    if org in {"primary", "original"}:
        base += 0.1
    elif org in {"recap", "commentary"}:
        base -= 0.15
    return _clamp01(base)


def _score_novelty(value: str) -> float:
    v = value.strip().lower()
    mapping = {
        "new": 1.0,
        "high": 0.9,
        "followup": 0.6,
        "medium": 0.6,
        "known": 0.35,
        "low": 0.35,
    }
    return mapping.get(v, 0.5)


def _score_price_alignment(event_polarity: str, price_change_pct: float | None) -> float:
    if price_change_pct is None:
        return 0.5
    p = event_polarity.strip().lower()
    if p in {"positive", "pos", "up"}:
        return 1.0 if price_change_pct >= 0 else 0.1
    if p in {"negative", "neg", "down"}:
        return 1.0 if price_change_pct <= 0 else 0.1
    return 0.5


def _score_issuer_specificity_v2(source: str, url: str, source_category: str) -> float:
    src = source.strip().lower()
    cat = source_category.strip()
    u = url.strip().lower()
    if src == "tdnet":
        return 1.0
    if src == "kabutan" and "/disclosures/pdf/" in u:
        return 0.85
    if cat in {"開示", "業績", "材料"}:
        return 0.68
    if cat in {"テク", "市況", "注目", "特集"}:
        return 0.25
    return 0.45


def _score_disclosure_channel(source: str, url: str, source_category: str, has_xbrl: bool | None) -> float:
    src = source.strip().lower()
    u = url.strip().lower()
    cat = source_category.strip()
    score = 0.4
    if src == "tdnet":
        score = 0.9
        if has_xbrl:
            score += 0.1
    elif src == "kabutan" and "/disclosures/pdf/" in u:
        score = 0.78
    elif src == "kabutan" and "/stock/news" in u:
        score = 0.5
    if cat in {"テク", "市況"}:
        score -= 0.2
    if cat in {"注目", "特集"}:
        score -= 0.15
    return _clamp01(score)


def _score_category_signal(source_category: str) -> float:
    cat = source_category.strip()
    mapping = {
        "開示": 1.0,
        "業績": 0.85,
        "材料": 0.8,
        "市況": 0.4,
        "テク": 0.25,
        "注目": 0.0,
        "特集": 0.0,
    }
    return mapping.get(cat, 0.5)


def _score_document_structure(
    source: str,
    url: str,
    has_xbrl: bool | None,
    has_update_history: bool | None,
) -> float:
    src = source.strip().lower()
    u = url.strip().lower()
    score = 0.5
    if src == "tdnet":
        score += 0.15
    if "/disclosures/pdf/" in u:
        score += 0.1
    if has_xbrl:
        score += 0.2
    if has_update_history:
        score -= 0.2
    return _clamp01(score)


def _normalize_text_for_match(value: str) -> str:
    s = unicodedata.normalize("NFKC", value or "").upper()
    for ch in (" ", "\u3000", "・", "　", "-", "－", "ｰ", "&", "＆", "(", ")", "（", "）", ":", "：", "　"):
        s = s.replace(ch, "")
    return s


def _score_name_match(title: str, aliases: list[str] | None) -> float:
    if not aliases:
        return 0.0
    t = _normalize_text_for_match(title)
    if not t:
        return 0.0
    for a in aliases:
        aa = _normalize_text_for_match(a)
        if aa and aa in t:
            return 1.0
    return 0.0


def rank_candidates(
    run_date: date,
    events: Iterable[CandidateEvent],
    *,
    price_change_pct: float | None = None,
    weights: ScoreWeights | None = None,
    mode: str = "v1",
    target_name_aliases: list[str] | None = None,
) -> list[RankedCandidate]:
    w = weights or ScoreWeights()
    ranked: list[RankedCandidate] = []
    for ev in events:
        s_time = _score_time_proximity(run_date, ev.published_at)
        s_conf = _clamp01(ev.confidence_base)
        if mode == "v2":
            s_source_rel = _score_primary_source(ev.source, ev.originality)
            s_spec = _score_issuer_specificity_v2(ev.source, ev.url, ev.source_category)
            s_channel = _score_disclosure_channel(ev.source, ev.url, ev.source_category, ev.has_xbrl)
            s_cat = _score_category_signal(ev.source_category)
            s_doc = _score_document_structure(ev.source, ev.url, ev.has_xbrl, ev.has_update_history)
            s_name = _score_name_match(ev.title, target_name_aliases)
            s_align = _score_price_alignment(ev.event_polarity, price_change_pct)
            score = (
                s_time * w.time_proximity
                + s_source_rel * w.source_reliability
                + s_spec * w.issuer_specificity
                + s_channel * w.disclosure_channel
                + s_cat * w.category_signal
                + s_doc * w.document_structure
                + s_name * w.name_match
                + s_align * w.price_alignment
                + s_conf * w.confidence_base
            )
            ranked.append(
                RankedCandidate(
                    event=ev,
                    cause_score=round(score, 6),
                    score_time_proximity=round(s_time, 6),
                    score_issuer_specificity=round(s_spec, 6),
                    score_material_strength=round(s_channel, 6),
                    score_primary_source=round(s_source_rel, 6),
                    score_novelty=round(s_cat, 6),
                    score_price_alignment=round(s_align, 6),
                    score_confidence_base=round(s_conf, 6),
                    score_source_reliability=round(s_source_rel, 6),
                    score_disclosure_channel=round(s_channel, 6),
                    score_category_signal=round(s_cat, 6),
                    score_document_structure=round(s_doc, 6),
                    score_name_match=round(s_name, 6),
                )
            )
        else:
            s_spec = _score_issuer_specificity(ev.issuer_specificity, ev.event_scope)
            s_material = _score_material_strength(ev.event_type)
            s_source = _score_primary_source(ev.source, ev.originality)
            s_novel = _score_novelty(ev.novelty_level)
            s_align = _score_price_alignment(ev.event_polarity, price_change_pct)
            score = (
                s_time * w.time_proximity
                + s_spec * w.issuer_specificity
                + s_material * w.material_strength
                + s_source * w.primary_source
                + s_novel * w.novelty
                + s_align * w.price_alignment
                + s_conf * w.confidence_base
            )
            ranked.append(
                RankedCandidate(
                    event=ev,
                    cause_score=round(score, 6),
                    score_time_proximity=round(s_time, 6),
                    score_issuer_specificity=round(s_spec, 6),
                    score_material_strength=round(s_material, 6),
                    score_primary_source=round(s_source, 6),
                    score_novelty=round(s_novel, 6),
                    score_price_alignment=round(s_align, 6),
                    score_confidence_base=round(s_conf, 6),
                )
            )
    ranked.sort(key=lambda x: x.cause_score, reverse=True)
    return ranked


def classify_cause_type(
    ranked: list[RankedCandidate],
    *,
    decision_threshold: float = 0.55,
    mode: str = "v1",
    a_threshold: float = 0.72,
) -> str:
    if not ranked:
        return "C"
    top = ranked[0]
    if top.cause_score < decision_threshold:
        return "C"
    if mode == "v2":
        if (
            top.cause_score >= a_threshold
            and (top.score_disclosure_channel or 0.0) >= 0.75
            and (top.score_category_signal or 0.0) >= 0.70
        ):
            return "A"
        return "B"
    spec = top.score_issuer_specificity
    material = top.score_material_strength
    if spec >= 0.8 and material >= 0.6:
        return "A"
    return "B"
