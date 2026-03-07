"""
ベンチETFキャッシュ確保ジョブ（Job2）。

TOPIX proxy: 1306.T
Nikkei225 proxy: 1321.T
不足時のみ重い取得、通常は差分取得。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.config import (
    get_buffer_days,
    get_rs_windows,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.utils.yf_cache import (
    MANIFEST_FILENAME,
    ensure_cache_with_incremental_fetch,
    load_manifest,
    update_manifest,
)

BENCHMARKS = {
    "topix": "1306.T",
    "nikkei": "1321.T",
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ensure index cache for benchmarks.")
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

    base = Path.cwd()
    cache_dir = get_yf_index_cache_dir(base)
    manifest_path = cache_dir / MANIFEST_FILENAME

    run_date = parse_run_date_opt(args.run_date)

    # required_days = max(RS_LOOKBACK_DAYS, Z_LOOKBACK_DAYS) + BUFFER_DAYS
    rs_windows = get_rs_windows()
    rs_max = max(rs_windows) if rs_windows else 252
    z_days = get_z_lookback_days()
    buffer_days = get_buffer_days()
    required_days = max(rs_max, z_days) + buffer_days

    print(f"キャッシュ出力: {cache_dir}", file=sys.stderr)
    print(f"required_days={required_days} (rs_max={rs_max}, z_days={z_days}, buffer={buffer_days})", file=sys.stderr)

    # manifestを1回だけ読み込む
    manifest = load_manifest(manifest_path)
    print(f"manifest読み込み完了: {len(manifest)}エントリ", file=sys.stderr)

    results = {}
    for bench_name, ticker in BENCHMARKS.items():
        cache_path = cache_dir / f"{bench_name}.csv"
        print(f"処理中: {bench_name} ({ticker})", file=sys.stderr)
        ent = ensure_cache_with_incremental_fetch(
            symbol=ticker,
            ticker=ticker,
            cache_path=cache_path,
            manifest=manifest,  # manifestを渡す（更新される）
            required_days=required_days,
            run_date=run_date,
            force=args.force,
        )
        results[bench_name] = ent
        status = ent.get("status", "unknown")
        bars = ent.get("fetched_bars", 0)
        print(f"  {bench_name}: status={status}, bars={bars}", file=sys.stderr)

    # manifestをまとめて更新（1回だけ）
    print(f"manifest更新中: {len(manifest)}エントリ", file=sys.stderr)
    update_manifest(manifest_path, manifest)
    print(f"manifest更新完了", file=sys.stderr)

    ok_count = sum(1 for r in results.values() if r.get("status") == "ok")
    print(f"完了: ok={ok_count}/{len(results)}", file=sys.stderr)

    if ok_count == 0:
        print("警告: すべてのベンチマーク取得に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
