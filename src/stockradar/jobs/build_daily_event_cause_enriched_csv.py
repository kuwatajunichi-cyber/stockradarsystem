"""
日次指標CSVにイベント要因列を付与して、render用CSVを生成する。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from stockradar.config import get_indicators_daily_dir
from stockradar.event_causes.selection_rules import filter_dataframe, resolve_selection_rules

UNKNOWN_CAUSE_TEXT = "材料不明・需給起因疑い"


def _find_latest_indicators(base: Path) -> Path | None:
    d = get_indicators_daily_dir(base)
    if not d.exists():
        return None
    files = sorted(d.glob("indicators_*.csv"))
    return files[-1] if files else None


def _auto_pick_z_column(df: pd.DataFrame) -> str:
    cols = [c for c in df.columns if c.startswith("z_turnover_")]
    if not cols:
        raise ValueError("z_turnover_* 列が見つかりません")
    cols.sort()
    return cols[-1]


def _norm_code(v: object) -> str:
    return str(v).strip().upper()


def _load_daily_cfg(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _resolve_path(base: Path, raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    return p


def _build_summary_map(summary_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for _, row in summary_df.iterrows():
        code = _norm_code(row.get("code", ""))
        if not code:
            continue
        out[code] = {
            "cause_type": str(row.get("cause_type", "")).strip(),
            "top_title": str(row.get("top_title", "")).strip(),
        }
    return out


def _build_top_n_candidates_map(
    cand_df: pd.DataFrame, top_n: int
) -> dict[str, list[dict[str, object]]]:
    """銘柄ごとにスコア上位 top_n 件の候補を返す。"""
    out: dict[str, list[dict[str, object]]] = {}
    if cand_df.empty or top_n < 1:
        return out
    working = cand_df.copy()
    if "rank" not in working.columns:
        working["rank"] = None
    if "cause_score" not in working.columns:
        working["cause_score"] = 0.0
    working["code_norm"] = working["code"].map(_norm_code)
    working = working.sort_values(
        by=["code_norm", "rank", "cause_score"], ascending=[True, True, False], na_position="last"
    )
    for _, row in working.iterrows():
        code = row["code_norm"]
        if not code:
            continue
        if code not in out:
            out[code] = []
        if len(out[code]) >= top_n:
            continue
        out[code].append({
            "title": str(row.get("event_title", "")).strip(),
            "url": str(row.get("event_url", "")).strip(),
            "source": str(row.get("event_source", "")).strip(),
            "score": row.get("cause_score"),
        })
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build enriched daily indicators CSV with event cause columns.")
    parser.add_argument("--run-date", type=str, help="対象日 YYYY-MM-DD（省略時: 今日）")
    parser.add_argument("--indicators", type=str, help="入力 indicators CSV（省略時: 最新）")
    parser.add_argument("--summary-csv", type=str, required=True, help="event_cause_summary_*.csv")
    parser.add_argument("--candidates-csv", type=str, required=True, help="event_cause_candidates_*.csv")
    parser.add_argument("--selection-config", type=str, default="config/event_cause_daily.yaml", help="抽出条件設定YAML")
    parser.add_argument("--z-column", type=str, default="", help="zscore列名（省略時は z_turnover_* から自動選択）")
    parser.add_argument("--z-threshold", type=float, default=3.5, help="抽出閾値（設定ファイル未存在時の後方互換用）")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="出力CSVパス（省略時: data/indicators/daily/indicators_event_enriched_YYYYMMDD.csv）",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()

    if args.indicators:
        indicators_path = _resolve_path(base, args.indicators)
    else:
        indicators_path = _find_latest_indicators(base)
        if indicators_path is None:
            print("エラー: indicators_*.csv が見つかりません", file=sys.stderr)
            sys.exit(1)
    if not indicators_path.exists():
        print(f"エラー: indicators が存在しません: {indicators_path}", file=sys.stderr)
        sys.exit(1)

    summary_path = _resolve_path(base, args.summary_csv)
    candidates_path = _resolve_path(base, args.candidates_csv)
    if not summary_path.exists():
        print(f"エラー: summary CSV が存在しません: {summary_path}", file=sys.stderr)
        sys.exit(1)
    if not candidates_path.exists():
        print(f"エラー: candidates CSV が存在しません: {candidates_path}", file=sys.stderr)
        sys.exit(1)

    indicators_df = pd.read_csv(indicators_path)
    z_col = args.z_column.strip() or _auto_pick_z_column(indicators_df)
    if z_col not in indicators_df.columns:
        print(f"エラー: 指定された z 列が存在しません: {z_col}", file=sys.stderr)
        sys.exit(1)

    cfg_path = _resolve_path(base, args.selection_config)
    daily_cfg = _load_daily_cfg(cfg_path)
    selection_rules = daily_cfg.get("selection_rules") if isinstance(daily_cfg.get("selection_rules"), dict) else None
    resolved_rules = resolve_selection_rules(selection_rules, z_column=z_col, z_threshold=args.z_threshold)
    target_df = filter_dataframe(indicators_df, resolved_rules)
    target_codes = {_norm_code(x) for x in target_df["code"].tolist() if _norm_code(x)}

    outputs_cfg = daily_cfg.get("outputs")
    top_n = 1
    if isinstance(outputs_cfg, dict) and "top_n" in outputs_cfg:
        try:
            top_n = max(1, int(outputs_cfg["top_n"]))
        except (TypeError, ValueError):
            pass

    summary_df = pd.read_csv(summary_path)
    cand_df = pd.read_csv(candidates_path)
    summary_map = _build_summary_map(summary_df)
    top_candidates_map = _build_top_n_candidates_map(cand_df, top_n)

    out_df = indicators_df.copy()
    out_df["event_cause_type"] = ""
    for i in range(1, top_n + 1):
        out_df[f"event_news_{i}_title"] = ""
        out_df[f"event_news_{i}_url"] = ""
        out_df[f"event_news_{i}_source"] = ""
        out_df[f"event_news_{i}_score"] = pd.NA

    for idx, row in out_df.iterrows():
        code = _norm_code(row.get("code", ""))
        if not code or code not in target_codes:
            continue

        summary = summary_map.get(code, {})
        cause_type = str(summary.get("cause_type", "")).strip().upper() or "C"
        out_df.at[idx, "event_cause_type"] = cause_type
        fallback_title = str(summary.get("top_title", "")).strip()

        if cause_type == "C":
            out_df.at[idx, "event_news_1_title"] = UNKNOWN_CAUSE_TEXT
            out_df.at[idx, "event_news_1_url"] = ""
            continue

        candidates = top_candidates_map.get(code, [])
        for i in range(1, top_n + 1):
            if i <= len(candidates):
                c = candidates[i - 1]
                title = str(c.get("title", "")).strip()
                if i == 1 and not title:
                    title = fallback_title or UNKNOWN_CAUSE_TEXT
                    if title == UNKNOWN_CAUSE_TEXT:
                        cause_type = "C"
                        out_df.at[idx, "event_cause_type"] = cause_type
                url = "" if (i == 1 and title == UNKNOWN_CAUSE_TEXT) else str(c.get("url", "")).strip()
                source = str(c.get("source", "")).strip()
                score = c.get("score")
                out_df.at[idx, f"event_news_{i}_title"] = title or ""
                out_df.at[idx, f"event_news_{i}_url"] = url
                out_df.at[idx, f"event_news_{i}_source"] = source
                out_df.at[idx, f"event_news_{i}_score"] = score if score is not None else pd.NA
            else:
                if i == 1 and fallback_title:
                    out_df.at[idx, f"event_news_{i}_title"] = fallback_title
                    out_df.at[idx, f"event_news_{i}_url"] = ""
                else:
                    out_df.at[idx, f"event_news_{i}_title"] = ""
                    out_df.at[idx, f"event_news_{i}_url"] = ""
                out_df.at[idx, f"event_news_{i}_source"] = ""
                out_df.at[idx, f"event_news_{i}_score"] = pd.NA

    if args.output.strip():
        output_path = _resolve_path(base, args.output.strip())
    else:
        out_dir = get_indicators_daily_dir(base)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"indicators_event_enriched_{run_date.strftime('%Y%m%d')}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"入力 indicators: {indicators_path}", file=sys.stderr)
    print(f"入力 summary: {summary_path} ({len(summary_df)}件)", file=sys.stderr)
    print(f"入力 candidates: {candidates_path} ({len(cand_df)}件)", file=sys.stderr)
    print(f"抽出条件: {resolved_rules}", file=sys.stderr)
    print(f"対象コード数: {len(target_codes)}", file=sys.stderr)
    print(f"出力: {output_path} ({len(out_df)}件)", file=sys.stderr)


if __name__ == "__main__":
    main()

