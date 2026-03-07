"""
equity_domestic_coreのOHLCVキャッシュ確保ジョブ（Job3）。

入力: equity_domestic_core_with_name.csv
各銘柄のOHLCVキャッシュを確保（不足時のみ重い取得）。
分割取得 + インターバル + リトライ + 途中再開（manifest）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.config import (
    get_buffer_days,
    get_rs_windows,
    get_yf_batch_size,
    get_yf_daily_cache_dir,
    get_yf_sleep_sec_between_batches,
    get_z_lookback_days,
)
from stockradar.utils.paths import (
    PATTERN_SETS_SECONDARY,
    find_latest_matching,
    get_universe_jpx_dir,
    load_codes_from_csv,
    ticker_for_code,
)
from stockradar.utils.yf_cache import (
    MANIFEST_FILENAME,
    ensure_cache_with_incremental_fetch,
    load_manifest,
    update_manifest,
)

import time


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Ensure yfinance daily cache for equity_domestic_core codes."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="equity_domestic_core_with_name.csv のパス（省略時は最新 sets_secondary_YYYYMMDD から自動選択）",
    )
    parser.add_argument(
        "--run-date",
        type=str,
        help="取得終了日（YYYY-MM-DD形式。省略時は今日）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="manifest のスキップを無視して全件再取得",
    )
    args = parser.parse_args(argv)

    run_date = parse_run_date_opt(args.run_date)

    base = Path.cwd()
    cache_dir = get_yf_daily_cache_dir(base)
    manifest_path = cache_dir / MANIFEST_FILENAME

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = base / input_path
    else:
        input_path = find_latest_matching(
            get_universe_jpx_dir(base),
            PATTERN_SETS_SECONDARY,
            "equity_domestic_core_with_name.csv",
        )
        if input_path is None:
            print(
                "エラー: equity_domestic_core_with_name.csv が見つかりません。"
                "data/universe/jpx/sets_secondary_YYYYMMDD/equity_domestic_core_with_name.csv を用意するか --input で指定してください。",
                file=sys.stderr,
            )
            sys.exit(1)

    if not input_path.exists():
        print(f"エラー: 入力が存在しません: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        codes = load_codes_from_csv(input_path)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    # required_days = max(RS_LOOKBACK_DAYS, Z_LOOKBACK_DAYS) + BUFFER_DAYS
    rs_windows = get_rs_windows()
    rs_max = max(rs_windows) if rs_windows else 252
    z_days = get_z_lookback_days()
    buffer_days = get_buffer_days()
    required_days = max(rs_max, z_days) + buffer_days
    batch_size = get_yf_batch_size()
    sleep_sec = get_yf_sleep_sec_between_batches()

    print(f"キャッシュ出力: {cache_dir}", file=sys.stderr)
    print(f"入力: {input_path} 銘柄数={len(codes)} required_days={required_days}", file=sys.stderr)

    # manifestを1回だけ読み込む
    manifest = load_manifest(manifest_path)
    print(f"manifest読み込み完了: {len(manifest)}エントリ", file=sys.stderr)

    # バッチ処理
    ok_count = 0
    fail_count = 0
    insuf_count = 0
    newly_fetched_days_list = []  # 新規取得日数を記録

    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        for code in batch:
            ticker = ticker_for_code(code)
            cache_path = cache_dir / f"{code}.csv"
            ent = ensure_cache_with_incremental_fetch(
                symbol=code,
                ticker=ticker,
                cache_path=cache_path,
                manifest=manifest,  # manifestを渡す（更新される）
                required_days=required_days,
                run_date=run_date,
                force=args.force,
            )
            status = ent.get("status", "unknown")
            if status == "ok":
                ok_count += 1
            elif status == "failed":
                fail_count += 1
            else:
                insuf_count += 1
            
            # 新規取得日数を記録（取得が行われた場合のみ）
            newly_fetched = ent.get("newly_fetched_days", 0)
            if newly_fetched > 0:
                newly_fetched_days_list.append(newly_fetched)
        if i + batch_size < len(codes):
            time.sleep(sleep_sec)

    # manifestをまとめて更新（1回だけ）
    print(f"manifest更新中: {len(manifest)}エントリ", file=sys.stderr)
    update_manifest(manifest_path, manifest)
    print(f"manifest更新完了", file=sys.stderr)

    # 新規取得日数の統計を表示
    if newly_fetched_days_list:
        min_days = min(newly_fetched_days_list)
        max_days = max(newly_fetched_days_list)
        avg_days = sum(newly_fetched_days_list) / len(newly_fetched_days_list)
        print(
            f"新規取得統計: 取得銘柄数={len(newly_fetched_days_list)}, "
            f"最小日数={min_days}, 最大日数={max_days}, 平均日数={avg_days:.1f}",
            file=sys.stderr,
        )
    else:
        print("新規取得統計: 取得銘柄数=0（すべてキャッシュから読み込み）", file=sys.stderr)

    print(f"完了: ok={ok_count} failed={fail_count} insufficient={insuf_count}", file=sys.stderr)

    if ok_count == 0:
        print("警告: すべての銘柄取得に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
