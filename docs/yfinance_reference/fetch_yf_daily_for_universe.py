"""
equity_domestic 銘柄リストを入力に、yfinance で日次（Close, Volume）を分割取得し、
キャッシュと manifest で途中再開・再実行を可能にするジョブ。

入力: equity_domestic.csv（--input で指定。未指定なら最新 sets_YYYYMMDD から探索）
required_days = max(IPO_LOOKBACK_DAYS, LIQ_LOOKBACK_DAYS)
キャッシュ: data/cache/yf_daily/{code}.csv
manifest: data/cache/yf_daily/_manifest.jsonl（1行1銘柄: code, requested_days, fetched_bars, status, error, fetched_at）

※ このフォルダは参考用コピーです。元: src/stockradar/jobs/fetch_yf_daily_for_universe.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import yfinance as yf

from stockradar.config import (
    get_ipo_lookback_days,
    get_liq_lookback_days,
    get_yf_batch_size,
    get_yf_daily_cache_dir,
    get_yf_retry_backoff_sec,
    get_yf_retry_max,
    get_yf_sleep_sec_between_batches,
)
from stockradar.utils.paths import (
    PATTERN_SETS,
    find_latest_matching,
    get_universe_jpx_dir,
    load_codes_from_csv,
    ticker_for_code,
)
from stockradar.utils.yf_cache import (
    MANIFEST_FILENAME,
    period_for_required_days,
    start_end_for_required_days,
)


def _load_manifest(manifest_path: Path) -> dict[str, dict]:
    """manifest を読んで code -> 最終エントリの辞書を返す。"""
    out: dict[str, dict] = {}
    if not manifest_path.exists():
        return out
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ent = json.loads(line)
                code = ent.get("code")
                if code:
                    out[code] = ent
            except json.JSONDecodeError:
                continue
    return out


def _write_manifest(manifest_path: Path, entries: dict[str, dict]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        for code in sorted(entries):
            f.write(json.dumps(entries[code], ensure_ascii=False) + "\n")


def _fetch_one(
    code: str,
    required_days: int,
    cache_dir: Path,
    retry_max: int,
    backoff_sec: list[int],
) -> dict:
    """
    1銘柄分を取得しキャッシュに書き、manifest 用エントリを返す。
    period で空の場合は start/end で再試行する（日本株等で安定しやすいため）。
    """
    ticker = ticker_for_code(code)
    period = period_for_required_days(required_days)
    start_dt, end_dt = start_end_for_required_days(required_days)
    csv_path = cache_dir / f"{code}.csv"
    now_iso = datetime.now(timezone.utc).isoformat()

    last_error: str | None = None
    for attempt in range(retry_max + 1):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period, interval="1d", auto_adjust=True)
            # 日本株等で period が空になることがあるため、start/end で再試行
            if hist is None or hist.empty:
                hist = t.history(
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=end_dt.strftime("%Y-%m-%d"),
                    interval="1d",
                    auto_adjust=True,
                )
            if hist is None or hist.empty:
                last_error = "empty_history"
                if attempt < retry_max:
                    time.sleep(backoff_sec[min(attempt, len(backoff_sec) - 1)])
                continue
            # 複数ティッカー時は MultiIndex になることがあるが、1銘柄なら通常の列名
            if hasattr(hist.columns, "levels"):
                hist = hist.copy()
                if hist.columns.nlevels > 1:
                    hist.columns = hist.columns.get_level_values(0)
            if "Close" not in hist.columns or "Volume" not in hist.columns:
                last_error = "missing_columns"
                if attempt < retry_max:
                    time.sleep(backoff_sec[min(attempt, len(backoff_sec) - 1)])
                continue
            # Open, High, Lowも取得（candle descriptor用）
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            available_cols = [col for col in required_cols if col in hist.columns]
            if len(available_cols) < 2:  # CloseとVolumeは最低限必要
                last_error = "missing_columns"
                if attempt < retry_max:
                    time.sleep(backoff_sec[min(attempt, len(backoff_sec) - 1)])
                continue
            df = hist[available_cols].copy()
            df.index = pd.to_datetime(df.index)
            # 重複日を落とす
            df = df[~df.index.duplicated(keep="first")]
            n_bars = len(df)
            if n_bars < required_days:
                last_error = f"insufficient_bars(n={n_bars})"
            cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(csv_path, encoding="utf-8-sig")
            return {
                "code": code,
                "requested_days": required_days,
                "fetched_bars": n_bars,
                "status": "ok" if n_bars >= required_days else "insufficient",
                "error": None if n_bars >= required_days else last_error,
                "fetched_at": now_iso,
            }
        except Exception as e:
            last_error = str(e)
            if attempt < retry_max:
                time.sleep(backoff_sec[min(attempt, len(backoff_sec) - 1)])

    return {
        "code": code,
        "requested_days": required_days,
        "fetched_bars": 0,
        "status": "failed",
        "error": last_error,
        "fetched_at": now_iso,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch yfinance daily (Close, Volume) for equity_domestic codes."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="equity_domestic.csv のパス（省略時は最新 sets_YYYYMMDD から自動選択）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="manifest のスキップを無視して全件再取得",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    cache_dir = get_yf_daily_cache_dir(base)
    manifest_path = cache_dir / MANIFEST_FILENAME

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = base / input_path
    else:
        input_path = find_latest_matching(
            get_universe_jpx_dir(base), PATTERN_SETS, "equity_domestic.csv"
        )
        if input_path is None:
            print(
                "エラー: equity_domestic.csv が見つかりません。"
                "data/universe/jpx/sets_YYYYMMDD/equity_domestic.csv を用意するか --input で指定してください。",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if not input_path.exists():
        print(f"エラー: 入力が存在しません: {input_path}", file=sys.stderr)
        raise SystemExit(1)

    try:
        codes = load_codes_from_csv(input_path)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        raise SystemExit(1)

    ipo_days = get_ipo_lookback_days()
    liq_days = get_liq_lookback_days()
    required_days = max(ipo_days, liq_days)
    batch_size = get_yf_batch_size()
    sleep_sec = get_yf_sleep_sec_between_batches()
    retry_max = get_yf_retry_max()
    backoff_sec = get_yf_retry_backoff_sec()

    manifest = _load_manifest(manifest_path)
    to_fetch = []
    for c in codes:
        if args.force:
            to_fetch.append(c)
            continue
        ent = manifest.get(c)
        if ent is None:
            to_fetch.append(c)
            continue
        if ent.get("status") == "ok" and ent.get("fetched_bars", 0) >= required_days:
            continue
        to_fetch.append(c)

    print(f"キャッシュ出力: {cache_dir}", file=sys.stderr)
    print(f"入力: {input_path} 銘柄数={len(codes)} required_days={required_days}", file=sys.stderr)
    print(f"スキップ済み: {len(codes) - len(to_fetch)} 取得対象: {len(to_fetch)}", file=sys.stderr)

    for i in range(0, len(to_fetch), batch_size):
        batch = to_fetch[i : i + batch_size]
        for code in batch:
            ent = _fetch_one(code, required_days, cache_dir, retry_max, backoff_sec)
            manifest[code] = ent
        if i + batch_size < len(to_fetch):
            time.sleep(sleep_sec)

    _write_manifest(manifest_path, manifest)
    ok = sum(1 for e in manifest.values() if e.get("status") == "ok")
    fail = sum(1 for e in manifest.values() if e.get("status") == "failed")
    insuf = sum(1 for e in manifest.values() if e.get("status") == "insufficient")
    print(f"manifest: {manifest_path} (ok={ok} failed={fail} insufficient={insuf})", file=sys.stderr)


if __name__ == "__main__":
    main()
