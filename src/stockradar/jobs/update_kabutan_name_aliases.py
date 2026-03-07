"""
月次ユニバース更新に合わせて別称辞書を更新するジョブ。

出力:
- aliases YAML
- alias_state JSON
- alias_delta CSV
- alias_summary JSON
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml

from stockradar.event_causes.name_alias_rules import (
    AliasThresholds,
    classify_confidence,
    dedup_key,
    evaluate_anomalies,
    is_valid_alias,
    normalize_alias,
    normalize_code,
)
from stockradar.sources.name_aliases_media import (
    FetchPolicy,
    MediaStats,
    fetch_kabutan_aliases_for_code,
    fetch_nikkei_aliases_for_code,
    fetch_reuters_aliases_for_code,
    fetch_tdnet_issuer_counts,
)
from stockradar.utils.stock_name_shortener import shorten_stock_name


@dataclass
class Candidate:
    alias: str
    sources: set[str]
    seen_count: int
    code: str
    name: str
    exists_in_base: bool
    confidence: str
    reason: str


def _parse_backoff(raw: str) -> list[int]:
    vals: list[int] = []
    for x in str(raw).split(","):
        s = x.strip()
        if not s:
            continue
        try:
            vals.append(int(s))
        except ValueError:
            continue
    return vals or [1000, 3000, 7000]


def _load_universe_rows(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"入力CSVが存在しません: {path}")
    df = pd.read_csv(path, dtype={"code": str})
    if "code" not in df.columns or "name" not in df.columns:
        raise ValueError(f"入力CSVに code/name 列がありません: {path}")
    out = df[["code", "name"]].copy()
    out["code"] = out["code"].astype(str).map(lambda x: normalize_code(x) or "")
    out["name"] = out["name"].astype(str).map(lambda x: x.strip())
    out = out[(out["code"] != "") & (out["name"] != "")]
    return out


def _load_alias_yaml(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    raw = cfg.get("aliases_by_code", {})
    out: dict[str, list[str]] = {}
    for code, vals in raw.items():
        c = normalize_code(str(code))
        if not c:
            continue
        arr = vals if isinstance(vals, list) else [vals]
        uniq: list[str] = []
        seen: set[str] = set()
        for a in arr:
            s = normalize_alias(str(a))
            if not s:
                continue
            dk = dedup_key(s)
            if dk in seen:
                continue
            seen.add(dk)
            uniq.append(s)
        if uniq:
            out[c] = uniq
    return out


def _load_state_json(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    root = data.get("aliases_by_code", {})
    out: dict[str, dict[str, dict[str, Any]]] = {}
    if not isinstance(root, dict):
        return out
    for code, recs in root.items():
        c = normalize_code(str(code))
        if not c or not isinstance(recs, dict):
            continue
        out[c] = {}
        for key, rec in recs.items():
            if not isinstance(rec, dict):
                continue
            out[c][str(key)] = rec
    return out


def _base_alias_norm_set(name: str, base_aliases: list[str]) -> set[str]:
    vals = [normalize_alias(name)]
    short = normalize_alias(shorten_stock_name(name))
    if short and short not in vals:
        vals.append(short)
    for a in base_aliases:
        vals.append(normalize_alias(a))
    return {dedup_key(v) for v in vals if v}


def _collect_candidates(
    *,
    universe: pd.DataFrame,
    base_aliases: dict[str, list[str]],
    base_state: dict[str, dict[str, dict[str, Any]]],
    media_list: list[str],
    tdnet_lookback_days: int,
    policy: FetchPolicy,
) -> tuple[dict[str, list[Candidate]], dict[str, MediaStats]]:
    per_code: dict[str, list[Candidate]] = {}
    code_name: dict[str, str] = {str(r.code): str(r.name) for r in universe.itertuples(index=False)}
    codes = sorted(code_name.keys())
    stats: dict[str, MediaStats] = {
        "kabutan": MediaStats(),
        "nikkei": MediaStats(),
        "reuters": MediaStats(),
        "tdnet": MediaStats(),
    }
    host_next_ts: dict[str, float] = {}
    rng = random.Random(20260307)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )

    tdnet_counts: dict[str, dict[str, int]] = {}
    if "tdnet" in media_list:
        run_d = date.today()
        start_d = run_d - timedelta(days=max(tdnet_lookback_days, 1))
        tdnet_counts = fetch_tdnet_issuer_counts(
            codes=set(codes),
            start_date=start_d,
            end_date=run_d,
            session=session,
            policy=policy,
            stats=stats["tdnet"],
            host_next_ts=host_next_ts,
            rng=rng,
        )

    for code in codes:
        name = code_name[code]
        exists = base_aliases.get(code, [])
        known_set = _base_alias_norm_set(name, exists)
        obs: dict[str, Candidate] = {}

        def add_obs(alias: str, source: str, count: int = 1) -> None:
            s = normalize_alias(alias)
            dk = dedup_key(s)
            if not s or not dk:
                return
            if dk in obs:
                obs[dk].sources.add(source)
                obs[dk].seen_count += count
                return
            exists_in_base = dk in known_set
            conf = classify_confidence(sources={source}, alias=s, exists_in_base=exists_in_base)
            reason = "exists_in_base" if exists_in_base else "new_candidate"
            obs[dk] = Candidate(
                alias=s,
                sources={source},
                seen_count=count,
                code=code,
                name=name,
                exists_in_base=exists_in_base,
                confidence=conf,
                reason=reason,
            )

        if "kabutan" in media_list:
            for a in fetch_kabutan_aliases_for_code(
                code, session=session, policy=policy, stats=stats["kabutan"], host_next_ts=host_next_ts, rng=rng
            ):
                add_obs(a, "kabutan")
        if "nikkei" in media_list:
            for a in fetch_nikkei_aliases_for_code(
                code, session=session, policy=policy, stats=stats["nikkei"], host_next_ts=host_next_ts, rng=rng
            ):
                add_obs(a, "nikkei")
        if "reuters" in media_list:
            for a in fetch_reuters_aliases_for_code(
                code, session=session, policy=policy, stats=stats["reuters"], host_next_ts=host_next_ts, rng=rng
            ):
                add_obs(a, "reuters")
        if "tdnet" in media_list:
            counts = tdnet_counts.get(code, {})
            for a, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:2]:
                add_obs(a, "tdnet", count=int(cnt))

        for dk, c in obs.items():
            c.confidence = classify_confidence(
                sources=c.sources,
                alias=c.alias,
                exists_in_base=c.exists_in_base,
            )
            c.reason = "invalid_alias" if not is_valid_alias(c.alias) else c.reason
            # bring historical state count if exists
            old = base_state.get(code, {}).get(dk, {})
            if isinstance(old, dict) and isinstance(old.get("seen_count"), int):
                c.seen_count += int(old.get("seen_count", 0))

        per_code[code] = list(obs.values())
    return per_code, stats


def _merge_aliases(
    *,
    universe: pd.DataFrame,
    base_aliases: dict[str, list[str]],
    candidates_by_code: dict[str, list[Candidate]],
    run_date: str,
) -> tuple[dict[str, list[str]], pd.DataFrame]:
    name_map = {str(r.code): str(r.name) for r in universe.itertuples(index=False)}
    merged: dict[str, list[str]] = {k: list(v) for k, v in base_aliases.items()}
    delta_rows: list[dict[str, Any]] = []
    conf_rank = {"high": 2, "medium": 1, "low": 0}
    for code in sorted(name_map.keys()):
        base_list = merged.get(code, [])
        existing_keys = {dedup_key(x) for x in base_list}
        cands = candidates_by_code.get(code, [])
        cands = sorted(
            cands,
            key=lambda c: (
                -conf_rank.get(c.confidence, 0),
                -int(c.seen_count),
                c.alias.lower(),
            ),
        )
        additions: list[str] = []
        for c in cands:
            dk = dedup_key(c.alias)
            if not dk:
                continue
            if dk in existing_keys:
                delta_rows.append(
                    {
                        "run_date": run_date,
                        "code": code,
                        "name": c.name,
                        "alias": c.alias,
                        "action": "skip",
                        "reason": "duplicate",
                        "confidence": c.confidence,
                        "sources": ",".join(sorted(c.sources)),
                        "seen_count": int(c.seen_count),
                    }
                )
                continue
            if c.confidence == "low":
                delta_rows.append(
                    {
                        "run_date": run_date,
                        "code": code,
                        "name": c.name,
                        "alias": c.alias,
                        "action": "review",
                        "reason": c.reason,
                        "confidence": c.confidence,
                        "sources": ",".join(sorted(c.sources)),
                        "seen_count": int(c.seen_count),
                    }
                )
                continue
            additions.append(c.alias)
            existing_keys.add(dk)
            delta_rows.append(
                {
                    "run_date": run_date,
                    "code": code,
                    "name": c.name,
                    "alias": c.alias,
                    "action": "add",
                    "reason": c.reason,
                    "confidence": c.confidence,
                    "sources": ",".join(sorted(c.sources)),
                    "seen_count": int(c.seen_count),
                }
            )
        if additions:
            merged.setdefault(code, [])
            merged[code].extend(additions)
    merged = {k: v for k, v in sorted(merged.items(), key=lambda kv: kv[0]) if v}
    return merged, pd.DataFrame(delta_rows)


def _build_state(
    *,
    merged_aliases: dict[str, list[str]],
    candidates_by_code: dict[str, list[Candidate]],
    previous_state: dict[str, dict[str, dict[str, Any]]],
    run_date: str,
) -> dict[str, Any]:
    now = run_date
    out: dict[str, dict[str, dict[str, Any]]] = {}
    candidate_map: dict[str, dict[str, Candidate]] = {}
    for code, vals in candidates_by_code.items():
        candidate_map[code] = {dedup_key(c.alias): c for c in vals}
    for code, aliases in merged_aliases.items():
        out[code] = {}
        prev = previous_state.get(code, {})
        for a in aliases:
            dk = dedup_key(a)
            cand = candidate_map.get(code, {}).get(dk)
            sources = sorted(cand.sources) if cand else sorted(prev.get(dk, {}).get("sources", []))
            seen_count = int(cand.seen_count) if cand else int(prev.get(dk, {}).get("seen_count", 1))
            confidence = cand.confidence if cand else str(prev.get(dk, {}).get("confidence", "medium"))
            first_seen = str(prev.get(dk, {}).get("first_seen", now))
            out[code][dk] = {
                "alias": a,
                "sources": sources,
                "first_seen": first_seen,
                "last_seen": now,
                "seen_count": seen_count,
                "confidence": confidence,
            }
    return {"aliases_by_code": out}


def _resolve_default_output(path_arg: str, default_path: Path) -> Path:
    p = Path(path_arg) if path_arg else default_path
    if not p.is_absolute():
        p = Path.cwd() / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Update kabutan_name_aliases.yaml from multi-media observations.")
    parser.add_argument("--input-core", type=str, required=True, help="equity_domestic_core_with_name.csv")
    parser.add_argument("--input-illiquid", type=str, required=True, help="equity_domestic_illiquid_with_name.csv")
    parser.add_argument("--input-ipo", type=str, required=True, help="equity_domestic_ipo_with_name.csv")
    parser.add_argument("--base-alias-yaml", type=str, default="config/kabutan_name_aliases.yaml")
    parser.add_argument("--base-state-json", type=str, default="data/cache/name_aliases/alias_state.json")
    parser.add_argument("--run-date", type=str, default=date.today().isoformat())
    parser.add_argument("--output-alias-yaml", type=str, default="config/kabutan_name_aliases.yaml")
    parser.add_argument("--output-state-json", type=str, default="data/cache/name_aliases/alias_state.json")
    parser.add_argument("--output-delta-csv", type=str, default="data/analysis/event_causes_poc/alias_delta.csv")
    parser.add_argument("--output-summary-json", type=str, default="data/analysis/event_causes_poc/alias_summary.json")
    parser.add_argument("--media", type=str, default="kabutan,nikkei,reuters,tdnet")
    parser.add_argument("--sleep-ms", type=int, default=800)
    parser.add_argument("--sleep-jitter-ms", type=int, default=400)
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--retry-backoff-ms", type=str, default="1000,3000,7000")
    parser.add_argument("--per-host-qps", type=float, default=0.0)
    parser.add_argument("--tdnet-lookback-days", type=int, default=120)
    parser.add_argument("--fail-on-anomaly", action="store_true")
    parser.add_argument("--added-aliases-max", type=int, default=400)
    parser.add_argument("--media-success-rate-min", type=float, default=0.85)
    parser.add_argument("--low-ratio-max", type=float, default=0.35)
    parser.add_argument("--resolved-monthly-tag", type=str, default="")
    parser.add_argument("--upstream-run-id", type=str, default="")
    args = parser.parse_args(argv)

    try:
        run_date = date.fromisoformat(args.run_date).isoformat()
    except ValueError:
        print(f"エラー: --run-date が不正です: {args.run_date}", file=sys.stderr)
        sys.exit(1)

    def _to_abs(path_str: str) -> Path:
        p = Path(path_str)
        return p if p.is_absolute() else Path.cwd() / p

    in_core = _to_abs(args.input_core)
    in_illiquid = _to_abs(args.input_illiquid)
    in_ipo = _to_abs(args.input_ipo)
    base_alias_path = _to_abs(args.base_alias_yaml)
    base_state_path = _to_abs(args.base_state_json)

    out_alias_path = _resolve_default_output(args.output_alias_yaml, base_alias_path)
    out_state_path = _resolve_default_output(args.output_state_json, base_state_path)
    out_delta_path = _resolve_default_output(args.output_delta_csv, Path("data/analysis/event_causes_poc/alias_delta.csv"))
    out_summary_path = _resolve_default_output(
        args.output_summary_json, Path("data/analysis/event_causes_poc/alias_summary.json")
    )

    media_list = [x.strip().lower() for x in args.media.split(",") if x.strip()]
    allowed = {"kabutan", "nikkei", "reuters", "tdnet"}
    media_list = [m for m in media_list if m in allowed]
    if not media_list:
        print("エラー: --media が空または不正です", file=sys.stderr)
        sys.exit(1)

    try:
        universe = pd.concat(
            [
                _load_universe_rows(in_core),
                _load_universe_rows(in_illiquid),
                _load_universe_rows(in_ipo),
            ],
            ignore_index=True,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"エラー: 入力読み込み失敗: {e}", file=sys.stderr)
        sys.exit(1)
    universe = universe.drop_duplicates(subset=["code"], keep="first")
    if universe.empty:
        print("エラー: 有効な code/name 行がありません", file=sys.stderr)
        sys.exit(1)

    base_aliases = _load_alias_yaml(base_alias_path)
    base_state = _load_state_json(base_state_path)

    policy = FetchPolicy(
        sleep_ms=max(args.sleep_ms, 0),
        sleep_jitter_ms=max(args.sleep_jitter_ms, 0),
        retry_max=max(args.retry_max, 1),
        retry_backoff_ms=_parse_backoff(args.retry_backoff_ms),
        per_host_qps=args.per_host_qps if args.per_host_qps > 0 else None,
    )
    candidates_by_code, media_stats = _collect_candidates(
        universe=universe,
        base_aliases=base_aliases,
        base_state=base_state,
        media_list=media_list,
        tdnet_lookback_days=args.tdnet_lookback_days,
        policy=policy,
    )
    merged_aliases, delta_df = _merge_aliases(
        universe=universe,
        base_aliases=base_aliases,
        candidates_by_code=candidates_by_code,
        run_date=run_date,
    )
    state = _build_state(
        merged_aliases=merged_aliases,
        candidates_by_code=candidates_by_code,
        previous_state=base_state,
        run_date=run_date,
    )

    out_alias_path.write_text(
        yaml.safe_dump({"aliases_by_code": merged_aliases}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    delta_df.to_csv(out_delta_path, index=False, encoding="utf-8-sig")
    out_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    add_cnt = int((delta_df["action"] == "add").sum()) if not delta_df.empty and "action" in delta_df.columns else 0
    low_cnt = (
        int((delta_df["action"] == "review").sum()) if not delta_df.empty and "action" in delta_df.columns else 0
    )
    all_observed = max(add_cnt + low_cnt, 1)
    low_ratio = low_cnt / float(all_observed)
    req = sum(s.requests for s in media_stats.values())
    succ = sum(s.success for s in media_stats.values())
    media_success_rate = 0.0 if req == 0 else succ / float(req)
    # False positive mitigation:
    # - evaluate success rate only on media with enough attempts
    # - skip success-rate anomaly when eligible media are too few
    min_requests_for_rate = 10
    eligible_media = [
        m for m in media_list if media_stats.get(m) is not None and media_stats[m].requests >= min_requests_for_rate
    ]
    elig_req = sum(media_stats[m].requests for m in eligible_media)
    elig_succ = sum(media_stats[m].success for m in eligible_media)
    effective_media_success_rate = media_success_rate if elig_req == 0 else (elig_succ / float(elig_req))
    enforce_media_success = len(eligible_media) >= 2
    thresholds = AliasThresholds(
        added_aliases_max=args.added_aliases_max,
        media_success_rate_min=args.media_success_rate_min,
        low_ratio_max=args.low_ratio_max,
    )
    anomalies = evaluate_anomalies(
        added_aliases=add_cnt,
        media_success_rate=effective_media_success_rate,
        low_ratio=low_ratio,
        thresholds=thresholds,
        enforce_media_success_rate=enforce_media_success,
    )
    summary = {
        "run_date": run_date,
        "resolved_monthly_tag": args.resolved_monthly_tag.strip(),
        "upstream_run_id": args.upstream_run_id.strip(),
        "inputs": {
            "core": str(in_core),
            "illiquid": str(in_illiquid),
            "ipo": str(in_ipo),
            "base_alias_yaml": str(base_alias_path),
            "base_state_json": str(base_state_path),
        },
        "outputs": {
            "alias_yaml": str(out_alias_path),
            "state_json": str(out_state_path),
            "delta_csv": str(out_delta_path),
            "summary_json": str(out_summary_path),
        },
        "counts": {
            "universe_codes": int(universe["code"].nunique()),
            "aliases_codes": len(merged_aliases),
            "added_aliases": add_cnt,
            "review_aliases": low_cnt,
            "delta_rows": int(len(delta_df)),
        },
        "rates": {
            "media_success_rate": media_success_rate,
            "effective_media_success_rate": effective_media_success_rate,
            "low_ratio": low_ratio,
        },
        "anomaly_context": {
            "enforce_media_success_rate": enforce_media_success,
            "eligible_media_for_success_rate": eligible_media,
            "min_requests_for_rate": min_requests_for_rate,
        },
        "media_stats": {k: v.as_dict() for k, v in media_stats.items() if k in media_list},
        "anomalies": anomalies,
    }
    out_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"aliases={out_alias_path} codes={len(merged_aliases)} added={add_cnt} review={low_cnt}",
        file=sys.stderr,
    )
    print(f"delta={out_delta_path} summary={out_summary_path}", file=sys.stderr)
    if anomalies:
        print("WARN: anomaly detected", file=sys.stderr)
        for a in anomalies:
            print(f"  - {a}", file=sys.stderr)
        if args.fail_on_anomaly:
            sys.exit(1)


if __name__ == "__main__":
    main()

