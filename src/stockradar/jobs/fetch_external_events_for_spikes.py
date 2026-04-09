"""
z_turnover 急増銘柄向けに、株探/TDnet からイベント候補 JSONL を自動生成する実験ジョブ。

日次運用では selection_rules 経由で接続。手動実行も可能。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import yaml

from stockradar.utils.core_indicators_csv import find_latest_core_indicators_csv
from stockradar.event_causes.selection_rules import filter_dataframe, resolve_selection_rules
from stockradar.sources.external_events import (
    ScrapedEvent,
    fetch_kabutan_news_for_month,
    fetch_tdnet_disclosures_for_date,
    filter_events_by_window,
)


def _auto_pick_z_col(df: pd.DataFrame) -> str:
    cols = [c for c in df.columns if c.startswith("z_turnover_")]
    if not cols:
        raise ValueError("z_turnover_* 列が見つかりません")
    cols.sort()
    return cols[-1]


def _load_selection_rules(config_path: Path) -> dict[str, object] | None:
    if not config_path.exists():
        return None
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    rules = cfg.get("selection_rules")
    return rules if isinstance(rules, dict) else None


def _month_keys(start_date: date, end_date: date) -> list[str]:
    keys: list[str] = []
    cur = date(start_date.year, start_date.month, 1)
    end_m = date(end_date.year, end_date.month, 1)
    while cur <= end_m:
        keys.append(cur.strftime("%Y%m00"))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return keys


def _event_to_record(e: ScrapedEvent) -> dict[str, object]:
    return {
        "code": e.code,
        "source": e.source,
        "published_at": e.published_at,
        "title": e.title,
        "raw_text_short": e.raw_text_short,
        "event_type": e.event_type,
        "event_polarity": e.event_polarity,
        "issuer_specificity": e.issuer_specificity,
        "novelty_level": e.novelty_level,
        "expected_impact_horizon": e.expected_impact_horizon,
        "confidence_base": e.confidence_base,
        "event_scope": e.event_scope,
        "originality": e.originality,
        "url": e.url,
        "source_category": e.source_category,
        "has_xbrl": e.has_xbrl,
        "listing_exchange": e.listing_exchange,
        "has_update_history": e.has_update_history,
    }


def _parse_cutoff_datetime(run_date: date, cutoff_time: str) -> datetime:
    txt = cutoff_time.strip()
    parts = txt.split(":")
    if len(parts) != 2:
        raise ValueError("cutoff-time は HH:MM 形式で指定してください（例: 15:30）")
    try:
        hh = int(parts[0])
        mm = int(parts[1])
    except ValueError as e:
        raise ValueError("cutoff-time は HH:MM 形式で指定してください（例: 15:30）") from e
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("cutoff-time が不正です（時: 0-23、分: 0-59）")
    return datetime.combine(run_date, time(hour=hh, minute=mm))


def _is_within_cutoff(e: ScrapedEvent, cutoff_dt: datetime | None) -> bool:
    if cutoff_dt is None:
        return True
    try:
        dt = datetime.fromisoformat(e.published_at)
    except ValueError:
        return False
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt <= cutoff_dt


def _event_identity_key(e: ScrapedEvent) -> tuple[str, str, str]:
    return (e.code, e.published_at, e.title.strip())


def _prefer_event(existing: ScrapedEvent, new: ScrapedEvent) -> ScrapedEvent:
    if existing.source == "tdnet":
        return existing
    if new.source == "tdnet":
        return new
    if new.confidence_base > existing.confidence_base:
        return new
    return existing


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch external events for z_turnover spike codes (PoC).")
    parser.add_argument("--run-date", type=str, help="対象日 YYYY-MM-DD（省略時: 今日）")
    parser.add_argument("--indicators", type=str, help="indicators_YYYYMMDD.csv（省略時: 最新）")
    parser.add_argument("--z-column", type=str, default="", help="zscore列（省略時は自動）")
    parser.add_argument("--z-threshold", type=float, default=4.0, help="抽出閾値")
    parser.add_argument(
        "--selection-config",
        type=str,
        default="config/event_cause_daily.yaml",
        help="抽出条件設定YAML（selection_rules）。未存在時は z-column/z-threshold を使用",
    )
    parser.add_argument("--lookback-days", type=int, default=20, help="イベント探索期間（日）")
    parser.add_argument("--cutoff-time", type=str, default="", help="当日採用カットオフ時刻（HH:MM、例: 15:30）")
    parser.add_argument(
        "--exclude-kabutan-categories",
        type=str,
        default="特集,注目",
        help="除外する株探カテゴリ（カンマ区切り、例: 特集,注目）",
    )
    parser.add_argument("--tdnet-max-pages", type=int, default=5, help="TDnet日別ページ最大走査数")
    parser.add_argument(
        "--output",
        type=str,
        default="data/external/events/news_tdnet_events.jsonl",
        help="出力JSONLパス",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    cutoff_dt = _parse_cutoff_datetime(run_date, args.cutoff_time) if args.cutoff_time.strip() else None

    indicators_path: Path | None
    if args.indicators:
        indicators_path = Path(args.indicators)
        if not indicators_path.is_absolute():
            indicators_path = base / indicators_path
    else:
        indicators_path = find_latest_core_indicators_csv(base)
        if indicators_path is None:
            print("エラー: indicators_*.csv が見つかりません", file=sys.stderr)
            sys.exit(1)
    assert indicators_path is not None
    if not indicators_path.exists():
        print(f"エラー: indicators が存在しません: {indicators_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(indicators_path)
    z_col = args.z_column.strip() or _auto_pick_z_col(df)
    if z_col not in df.columns:
        print(f"エラー: z列がありません: {z_col}", file=sys.stderr)
        sys.exit(1)
    selection_cfg_path = Path(args.selection_config)
    if not selection_cfg_path.is_absolute():
        selection_cfg_path = base / selection_cfg_path
    raw_rules = _load_selection_rules(selection_cfg_path)
    resolved_rules = resolve_selection_rules(raw_rules, z_column=z_col, z_threshold=args.z_threshold)

    spikes = filter_dataframe(df, resolved_rules)
    if spikes.empty:
        print("対象なし: selection_rules に一致する銘柄がありません", file=sys.stderr)
        return

    target_codes = sorted({str(x).strip().upper() for x in spikes["code"].tolist() if str(x).strip()})
    start_date = run_date - timedelta(days=max(1, args.lookback_days))
    end_date = run_date
    excluded_categories = {x.strip() for x in args.exclude_kabutan_categories.split(",") if x.strip()}

    # 株探（銘柄×月）
    kabutan_events: list[ScrapedEvent] = []
    month_keys = _month_keys(start_date, end_date)
    for code in target_codes:
        for mk in month_keys:
            try:
                evs = fetch_kabutan_news_for_month(code=code, yyyymm00=mk, nmode=0)
            except Exception as e:
                print(f"警告: 株探取得失敗 code={code} month={mk}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            kabutan_events.extend(evs)
    kabutan_events = filter_events_by_window(kabutan_events, start_date, end_date)
    kabutan_events = [e for e in kabutan_events if e.code in target_codes]
    kabutan_before_cat = len(kabutan_events)
    kabutan_events = [e for e in kabutan_events if e.source_category not in excluded_categories]
    kabutan_excluded_by_cat = kabutan_before_cat - len(kabutan_events)

    # TDnet（日付×ページ）→ 対象コードで絞り込み
    tdnet_events: list[ScrapedEvent] = []
    d = start_date
    while d <= end_date:
        try:
            day_events = fetch_tdnet_disclosures_for_date(d, max_pages=max(1, args.tdnet_max_pages))
        except Exception as e:
            print(f"警告: TDnet取得失敗 date={d.isoformat()}: {type(e).__name__}: {e}", file=sys.stderr)
            d += timedelta(days=1)
            continue
        tdnet_events.extend([ev for ev in day_events if ev.code in target_codes])
        d += timedelta(days=1)

    all_events = kabutan_events + tdnet_events
    all_events = [ev for ev in all_events if _is_within_cutoff(ev, cutoff_dt)]
    filtered_count = len(all_events)

    # 重複除去（code, published_at, title）
    # 株探とTDnetで重複する場合はTDnetを優先する。
    dedup_map: dict[tuple[str, str, str], ScrapedEvent] = {}
    for ev in all_events:
        k = _event_identity_key(ev)
        prev = dedup_map.get(k)
        if prev is None:
            dedup_map[k] = ev
            continue
        dedup_map[k] = _prefer_event(prev, ev)
    uniq = list(dedup_map.values())
    dedup_removed = filtered_count - len(uniq)
    uniq.sort(key=lambda x: (x.code, x.published_at, x.source))

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = base / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ev in uniq:
            f.write(json.dumps(_event_to_record(ev), ensure_ascii=False) + "\n")

    print(f"入力 indicators: {indicators_path}", file=sys.stderr)
    print(f"抽出設定: {selection_cfg_path if selection_cfg_path.exists() else '(default z-threshold)'}", file=sys.stderr)
    print(f"抽出条件: {json.dumps(resolved_rules, ensure_ascii=False)}", file=sys.stderr)
    print(f"対象コード数: {len(target_codes)}", file=sys.stderr)
    print(f"探索期間: {start_date} ~ {end_date}", file=sys.stderr)
    if cutoff_dt is not None:
        print(f"当日カットオフ: {cutoff_dt.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
    print(f"株探カテゴリ除外: {sorted(excluded_categories)}", file=sys.stderr)
    print(f"株探イベント: {len(kabutan_events)}", file=sys.stderr)
    print(f"株探カテゴリ除外件数: {kabutan_excluded_by_cat}", file=sys.stderr)
    print(f"TDnetイベント: {len(tdnet_events)}", file=sys.stderr)
    print(f"時刻フィルタ後イベント: {filtered_count}", file=sys.stderr)
    print(f"重複除去件数: {dedup_removed}", file=sys.stderr)
    print(f"出力: {output_path} ({len(uniq)}件)", file=sys.stderr)


if __name__ == "__main__":
    main()
