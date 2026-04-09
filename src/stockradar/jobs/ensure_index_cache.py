"""
ベンチマークキャッシュ確保ジョブ（Job2）。

TOPIX: 1475.T
Nikkei225: ^N225
不足時のみ重い取得、通常は差分取得。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.config import (
    get_buffer_days,
    get_rs_windows,
    get_stale_retry_max_passes,
    get_stale_retry_sleep_sec,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.utils.yf_cache import (
    MANIFEST_FILENAME,
    ensure_cache_with_incremental_fetch,
    load_manifest,
    rebuild_manifest_entry_from_disk,
    update_manifest,
)

BENCHMARKS = {
    "topix": "1475.T",
    "nikkei": "^N225",
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
    print(f"整合確認: run_date={run_date.isoformat() if run_date else 'today'}", file=sys.stderr)

    # manifestを1回だけ読み込む
    manifest = load_manifest(manifest_path)
    print(f"manifest読み込み完了: {len(manifest)}エントリ", file=sys.stderr)

    max_passes = get_stale_retry_max_passes()
    stale_sleep = get_stale_retry_sleep_sec()
    bench_order = list(BENCHMARKS.keys())

    def _manifest_status(ticker: str) -> str:
        return str(manifest.get(ticker, {}).get("status", "missing"))

    def _summarize() -> dict[str, int]:
        ok_c = fail_c = insuf_c = stale_c = 0
        for bn in bench_order:
            st = _manifest_status(BENCHMARKS[bn])
            if st == "ok":
                ok_c += 1
            elif st == "failed":
                fail_c += 1
            elif st == "stale":
                stale_c += 1
            else:
                insuf_c += 1
        return {
            "ok": ok_c,
            "failed": fail_c,
            "insufficient": insuf_c,
            "stale": stale_c,
        }

    results: dict[str, dict] = {}
    for pass_i in range(max_passes):
        if pass_i > 0:
            if run_date is None:
                break
            stale_benches = [
                bn
                for bn in bench_order
                if _manifest_status(BENCHMARKS[bn]) == "stale"
            ]
            stats = _summarize()
            print(
                f"ensure_index_cache: stale 再試行 {pass_i + 1}/{max_passes} "
                f"対象={stale_benches} "
                f"(ok={stats['ok']} stale={stats['stale']} "
                f"insufficient={stats['insufficient']} failed={stats['failed']})",
                file=sys.stderr,
            )
            if not stale_benches:
                break
            time.sleep(stale_sleep)
            pending = stale_benches
        else:
            pending = bench_order

        for bench_name in pending:
            ticker = BENCHMARKS[bench_name]
            cache_path = cache_dir / f"{bench_name}.csv"
            print(f"処理中: {bench_name} ({ticker})", file=sys.stderr)
            ent = ensure_cache_with_incremental_fetch(
                symbol=ticker,
                ticker=ticker,
                cache_path=cache_path,
                manifest=manifest,
                required_days=required_days,
                run_date=run_date,
                force=args.force,
            )
            results[bench_name] = ent
            status = ent.get("status", "unknown")
            bars = ent.get("fetched_bars", 0)
            print(f"  {bench_name}: status={status}, bars={bars}", file=sys.stderr)

        if pass_i == 0 and run_date is not None:
            s0 = _summarize()
            print(
                f"ensure_index_cache: 初回パス完了 ok={s0['ok']} stale={s0['stale']} "
                f"insufficient={s0['insufficient']} failed={s0['failed']}",
                file=sys.stderr,
            )

    reconcile_at = datetime.now(timezone.utc).isoformat()
    reconcile_changes = 0
    for bn in bench_order:
        ticker = BENCHMARKS[bn]
        cache_path = cache_dir / f"{bn}.csv"
        rebuilt = rebuild_manifest_entry_from_disk(
            ticker,
            cache_path,
            requested_days=required_days,
            run_date=run_date,
            fetched_at=reconcile_at,
        )
        old = manifest.get(ticker)
        if old is None or (
            old.get("status") != rebuilt.get("status")
            or old.get("fetched_bars") != rebuilt.get("fetched_bars")
            or (old.get("error") or "") != (rebuilt.get("error") or "")
        ):
            reconcile_changes += 1
        manifest[ticker] = rebuilt
    if reconcile_changes > 0:
        print(
            f"ensure_index_cache: ディスク照合で manifest を {reconcile_changes} 件同期修正",
            file=sys.stderr,
        )

    # ベンチティッカー変更時に古い manifest 行を残さない（このディレクトリはベンチ専用）
    allowed = set(BENCHMARKS.values())
    manifest = {sym: ent for sym, ent in manifest.items() if sym in allowed}

    # manifestをまとめて更新（1回だけ）
    print(f"manifest更新中: {len(manifest)}エントリ", file=sys.stderr)
    update_manifest(manifest_path, manifest)
    print(f"manifest更新完了", file=sys.stderr)

    final = _summarize()
    ok_count = final["ok"]
    stale_count = final["stale"]
    print(
        f"完了: ok={ok_count}/{len(bench_order)} "
        f"(insufficient={final['insufficient']} stale={stale_count} failed={final['failed']})",
        file=sys.stderr,
    )

    if run_date is not None and stale_count > 0:
        print(
            f"エラー: ensure_index_cache stale が {stale_count} 件残存 "
            f"（データ未反映・遅延の可能性。人手確認または翌営業日に再実行）",
            file=sys.stderr,
        )
        sys.exit(2)

    if ok_count == 0:
        print("警告: すべてのベンチマーク取得に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
