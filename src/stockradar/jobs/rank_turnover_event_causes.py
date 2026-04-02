"""
売買代金zscore急増銘柄の背景候補を順位付けする PoC ジョブ。

日次運用では selection_rules 経由で接続。手動実行も可能。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from stockradar.utils.core_indicators_csv import find_latest_core_indicators_csv
from stockradar.event_causes import (
    CandidateEvent,
    ScoreWeights,
    classify_cause_type,
    rank_candidates,
)
from stockradar.event_causes.selection_rules import filter_dataframe, resolve_selection_rules
from stockradar.utils.stock_name_shortener import shorten_stock_name


def _load_events_jsonl(path: Path) -> list[CandidateEvent]:
    events: list[CandidateEvent] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = line.strip()
            if not row:
                continue
            try:
                rec = json.loads(row)
            except json.JSONDecodeError:
                continue
            code = str(rec.get("code", "")).strip()
            if not code:
                continue
            events.append(
                CandidateEvent(
                    code=code,
                    source=str(rec.get("source", "")).strip().lower() or "unknown",
                    published_at=str(rec.get("published_at", "")).strip(),
                    title=str(rec.get("title", "")).strip(),
                    raw_text_short=str(rec.get("raw_text_short", "")).strip(),
                    event_type=str(rec.get("event_type", "")).strip().lower() or "other",
                    event_polarity=str(rec.get("event_polarity", "")).strip().lower() or "neutral",
                    issuer_specificity=str(rec.get("issuer_specificity", "")).strip().lower() or "medium",
                    novelty_level=str(rec.get("novelty_level", "")).strip().lower() or "medium",
                    expected_impact_horizon=str(rec.get("expected_impact_horizon", "")).strip().lower(),
                    confidence_base=float(rec.get("confidence_base", 0.5) or 0.5),
                    event_scope=str(rec.get("event_scope", "")).strip().lower(),
                    originality=str(rec.get("originality", "")).strip().lower(),
                    url=str(rec.get("url", "")).strip(),
                    source_category=str(rec.get("source_category", "")).strip(),
                    has_xbrl=bool(rec.get("has_xbrl")) if "has_xbrl" in rec else None,
                    listing_exchange=str(rec.get("listing_exchange", "")).strip(),
                    has_update_history=bool(rec.get("has_update_history")) if "has_update_history" in rec else None,
                )
            )
    return events


def _load_weights(path: Path | None, mode: str) -> tuple[str, ScoreWeights]:
    if path is None or not path.exists():
        if mode == "v2":
            return "v2", ScoreWeights(
                time_proximity=0.25,
                issuer_specificity=0.12,
                confidence_base=0.03,
                source_reliability=0.18,
                disclosure_channel=0.18,
                category_signal=0.17,
                document_structure=0.07,
                name_match=0.15,
                price_alignment=0.0,
            )
        return "v1", ScoreWeights()
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    resolved_mode = mode
    if resolved_mode == "auto":
        resolved_mode = str(cfg.get("scoring_mode", "v1")).strip().lower() or "v1"
    if resolved_mode == "v2":
        w = cfg.get("weights_v2", cfg.get("weights", {}))
        return "v2", ScoreWeights(
            time_proximity=float(w.get("time_proximity", 0.25)),
            issuer_specificity=float(w.get("issuer_specificity", 0.12)),
            confidence_base=float(w.get("confidence_base", 0.03)),
            source_reliability=float(w.get("source_reliability", 0.18)),
            disclosure_channel=float(w.get("disclosure_channel", 0.18)),
            category_signal=float(w.get("category_signal", 0.17)),
            document_structure=float(w.get("document_structure", 0.07)),
            name_match=float(w.get("name_match", 0.15)),
            price_alignment=float(w.get("price_alignment", 0.0)),
        )
    w = cfg.get("weights_v1", cfg.get("weights", {}))
    return "v1", ScoreWeights(
        time_proximity=float(w.get("time_proximity", 0.24)),
        issuer_specificity=float(w.get("issuer_specificity", 0.20)),
        material_strength=float(w.get("material_strength", 0.20)),
        primary_source=float(w.get("primary_source", 0.12)),
        novelty=float(w.get("novelty", 0.12)),
        price_alignment=float(w.get("price_alignment", 0.08)),
        confidence_base=float(w.get("confidence_base", 0.04)),
    )


def _auto_pick_z_column(df: pd.DataFrame) -> str:
    candidates = [c for c in df.columns if c.startswith("z_turnover_")]
    if not candidates:
        raise ValueError("z_turnover_* 列が見つかりません")
    candidates.sort()
    return candidates[-1]


def _load_name_aliases(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    raw = cfg.get("aliases_by_code", {})
    out: dict[str, list[str]] = {}
    for code, aliases in raw.items():
        c = str(code).strip().upper()
        if not c:
            continue
        if isinstance(aliases, list):
            vals = [str(x).strip() for x in aliases if str(x).strip()]
        else:
            vals = [str(aliases).strip()] if str(aliases).strip() else []
        out[c] = vals
    return out


def _load_selection_rules(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    rules = cfg.get("selection_rules")
    return rules if isinstance(rules, dict) else None


def _load_daily_cfg(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _build_name_alias_candidates(name: str, manual_aliases: list[str] | None) -> list[str]:
    base = str(name or "").strip()
    aliases: list[str] = []
    if base:
        aliases.append(base)
        short = shorten_stock_name(base)
        if short and short not in aliases:
            aliases.append(short)
    if manual_aliases:
        for a in manual_aliases:
            s = str(a).strip()
            if s and s not in aliases:
                aliases.append(s)
    return aliases


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rank background event candidates for z_turnover spikes (PoC).")
    parser.add_argument("--run-date", type=str, help="対象日 YYYY-MM-DD（省略時: 今日）")
    parser.add_argument("--indicators", type=str, help="indicators_YYYYMMDD.csv のパス（省略時: 最新）")
    parser.add_argument(
        "--events-jsonl",
        type=str,
        default="data/external/events/news_tdnet_events.jsonl",
        help="候補イベント JSONL（1行1イベント）",
    )
    parser.add_argument("--config", type=str, default="config/event_cause_poc.yaml", help="PoC重み設定YAML")
    parser.add_argument("--z-column", type=str, default="", help="zscore列名（省略時は z_turnover_* から自動選択）")
    parser.add_argument("--z-threshold", type=float, default=4.0, help="トリガー閾値（default: 4.0）")
    parser.add_argument("--decision-threshold", type=float, default=None, help="A/B/C判定閾値")
    parser.add_argument("--a-threshold", type=float, default=None, help="A判定閾値（v2モード用）")
    parser.add_argument("--scoring-mode", type=str, default="auto", help="scoring mode: auto/v1/v2")
    parser.add_argument("--output-suffix", type=str, default="", help="出力ファイル名サフィックス（例: _v2）")
    parser.add_argument(
        "--selection-config",
        type=str,
        default="config/event_cause_daily.yaml",
        help="抽出条件設定YAML（selection_rules）",
    )
    parser.add_argument(
        "--name-alias-config",
        type=str,
        default="config/kabutan_name_aliases.yaml",
        help="銘柄略称辞書YAML（code -> aliases）",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()

    if args.indicators:
        indicators_path = Path(args.indicators)
        if not indicators_path.is_absolute():
            indicators_path = base / indicators_path
    else:
        indicators_path = find_latest_core_indicators_csv(base)
        if indicators_path is None:
            print("エラー: indicators_*.csv が見つかりません", file=sys.stderr)
            sys.exit(1)

    if not indicators_path.exists():
        print(f"エラー: indicators ファイルが見つかりません: {indicators_path}", file=sys.stderr)
        sys.exit(1)

    indicators_df = pd.read_csv(indicators_path)
    z_col = args.z_column.strip() or _auto_pick_z_column(indicators_df)
    if z_col not in indicators_df.columns:
        print(f"エラー: 指定された z 列が存在しません: {z_col}", file=sys.stderr)
        sys.exit(1)

    selection_cfg_path = Path(args.selection_config)
    if not selection_cfg_path.is_absolute():
        selection_cfg_path = base / selection_cfg_path
    daily_cfg = _load_daily_cfg(selection_cfg_path)
    selection_rules = _load_selection_rules(selection_cfg_path)
    resolved_rules = resolve_selection_rules(selection_rules, z_column=z_col, z_threshold=args.z_threshold)
    filtered = filter_dataframe(indicators_df, resolved_rules)
    if filtered.empty:
        print("対象なし: selection_rules に一致する銘柄がありません", file=sys.stderr)
        return

    events_path = Path(args.events_jsonl)
    if not events_path.is_absolute():
        events_path = base / events_path
    events = _load_events_jsonl(events_path)
    events_by_code: dict[str, list[CandidateEvent]] = defaultdict(list)
    for ev in events:
        events_by_code[ev.code].append(ev)

    config_arg = args.config.strip()
    if config_arg == "config/event_cause_poc.yaml":
        weights_source = str(daily_cfg.get("weights_source", "config/event_cause_poc.yaml")).strip() or "config/event_cause_poc.yaml"
    else:
        weights_source = config_arg
    cfg_path = Path(weights_source)
    if not cfg_path.is_absolute():
        cfg_path = base / cfg_path
    scoring_mode_arg = args.scoring_mode.strip().lower()
    if scoring_mode_arg == "auto" and str(daily_cfg.get("scoring_mode", "")).strip():
        scoring_mode_arg = str(daily_cfg.get("scoring_mode")).strip().lower()
    scoring_mode, weights = _load_weights(cfg_path, scoring_mode_arg)

    decision_threshold = args.decision_threshold
    if decision_threshold is None:
        decision_threshold = float(daily_cfg.get("decision_threshold", 0.55))
    a_threshold = args.a_threshold
    if a_threshold is None:
        a_threshold = float(daily_cfg.get("a_threshold", 0.72))

    alias_cfg_path = Path(args.name_alias_config)
    if not alias_cfg_path.is_absolute():
        alias_cfg_path = base / alias_cfg_path
    aliases_by_code = _load_name_aliases(alias_cfg_path)

    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []

    for _, row in filtered.iterrows():
        code = str(row["code"]).strip()
        name = str(row.get("name", "")).strip()
        ohlc_as_of = ""
        if "date" in row.index and pd.notna(row["date"]):
            ohlc_as_of = str(row["date"]).strip()
        price_change_pct = None
        if "price_change_pct" in row and pd.notna(row["price_change_pct"]):
            try:
                price_change_pct = float(row["price_change_pct"])
            except (TypeError, ValueError):
                price_change_pct = None
        ranked = rank_candidates(
            run_date,
            events_by_code.get(code, []),
            price_change_pct=price_change_pct,
            weights=weights,
            mode=scoring_mode,
            target_name_aliases=_build_name_alias_candidates(name, aliases_by_code.get(code)),
        )
        cause_type = classify_cause_type(
            ranked,
            decision_threshold=decision_threshold,
            mode=scoring_mode,
            a_threshold=a_threshold,
        )
        top = ranked[0] if ranked else None

        summary_rows.append(
            {
                "date": run_date.isoformat(),
                "ohlc_as_of": ohlc_as_of,
                "code": code,
                "name": name,
                "z_column": z_col,
                "z_value": float(row[z_col]),
                "cause_type": cause_type,
                "top_score": top.cause_score if top else 0.0,
                "top_source": top.event.source if top else "",
                "top_event_type": top.event.event_type if top else "",
                "top_title": top.event.title if top else "",
                "candidate_count": len(ranked),
                "scoring_mode": scoring_mode,
            }
        )

        for rank, cand in enumerate(ranked, start=1):
            rec = {
                "date": run_date.isoformat(),
                "ohlc_as_of": ohlc_as_of,
                "code": code,
                "name": name,
                "rank": rank,
                "cause_type": cause_type,
                "cause_score": cand.cause_score,
                "score_time_proximity": cand.score_time_proximity,
                "score_issuer_specificity": cand.score_issuer_specificity,
                "score_material_strength": cand.score_material_strength,
                "score_primary_source": cand.score_primary_source,
                "score_novelty": cand.score_novelty,
                "score_price_alignment": cand.score_price_alignment,
                "score_confidence_base": cand.score_confidence_base,
                "score_source_reliability": cand.score_source_reliability,
                "score_disclosure_channel": cand.score_disclosure_channel,
                "score_category_signal": cand.score_category_signal,
                "score_document_structure": cand.score_document_structure,
                "scoring_mode": scoring_mode,
            }
            rec.update({f"event_{k}": v for k, v in asdict(cand.event).items()})
            detail_rows.append(rec)

    out_dir = base / "data" / "analysis" / "event_causes_poc"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = run_date.strftime("%Y%m%d")
    out_suffix = args.output_suffix.strip()
    summary_path = out_dir / f"event_cause_summary_{suffix}{out_suffix}.csv"
    detail_path = out_dir / f"event_cause_candidates_{suffix}{out_suffix}.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(detail_rows).to_csv(detail_path, index=False, encoding="utf-8-sig")

    print(f"入力 indicators: {indicators_path}", file=sys.stderr)
    print(f"入力 events: {events_path} ({len(events)}件)", file=sys.stderr)
    print(f"抽出設定: {selection_cfg_path if selection_cfg_path.exists() else '(default z-threshold)'}", file=sys.stderr)
    print(f"抽出条件: {json.dumps(resolved_rules, ensure_ascii=False)}", file=sys.stderr)
    print(f"出力 summary: {summary_path} ({len(summary_rows)}件)", file=sys.stderr)
    print(f"出力 detail: {detail_path} ({len(detail_rows)}件)", file=sys.stderr)


if __name__ == "__main__":
    main()
