"""
指標算出ジョブ（Job4）。

入力: equity_domestic_core_with_name.csv、data/cache/yf_daily/、data/cache/yf_index/
出力: data/indicators/daily/indicators_YYYYMMDD.csv

指標:
- 出来高zscore（売買代金近似ベース）
- 各サイトへのリンク（株探・みんかぶ・バフェット・Yahoo）
- RS（B方式：期間リターン差）
- 短期RS加速（Short-term RS Acceleration）：短期RSと長期RSの差
- 短期RS加速のzscore：短期RS加速を標準化窓で標準化した値
- β調整RS（Market-adjusted Excess Return）：市場寄与分を差し引いた純粋な銘柄固有要因の強さ
- 情報比率（Information Ratio）：日次超過リターンの平均を標準偏差で割った値
- 売買代金の移動平均比：当日売買代金 ÷ 直近 Z_LOOKBACK_DAYS 営業日の売買代金平均（窓は出来高 z と同一）
- 騰落率（前日比）：終値の前営業日終値に対する変化率（百分率）
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from collections.abc import Callable

import pandas as pd

from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.config import (
    get_indicators_daily_dir,
    get_indicators_max_workers,
    get_rs_benchmark,
    get_rs_windows,
    get_yf_daily_cache_dir,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.indicators.date_anchor import build_anchor_context, prepare_asof_series, merged_close
from stockradar.indicators.risk_adjusted import (
    compute_beta_adjusted_rs_from_merged,
    compute_information_ratio_from_merged,
)
from stockradar.indicators.rs import (
    compute_rs_acceleration_from_merged,
    compute_rs_acceleration_zscore_from_merged,
    compute_rs_from_merged,
)
from stockradar.indicators.zscore import (
    compute_turnover_ma_ratio_from_prepared,
    compute_zscore_turnover_from_prepared,
)
from stockradar.utils.external_links import build_external_links
from stockradar.utils.paths import (
    PATTERN_SETS_SECONDARY,
    find_latest_matching,
    get_universe_jpx_dir,
)
from stockradar.utils.yf_cache import load_cache

STALE_EXCLUSIONS_FILENAME = "_stale_exclusions.json"
_WORKER_CTX: dict = {}

# candle_descriptorのインポート（オプション）
compute_candle_descriptors: Callable[[pd.DataFrame], tuple[str, str]] | None
try:
    from stockradar.utils.candle_descriptor import compute_candle_descriptors as _compute_candle_descriptors
    compute_candle_descriptors = _compute_candle_descriptors
except ImportError:
    compute_candle_descriptors = None


def _load_codes_with_names(path: Path) -> pd.DataFrame:
    """code, name列を含むDataFrameを返す。"""
    df = pd.read_csv(path)
    if "code" not in df.columns:
        raise ValueError(f"入力CSVに code 列がありません: {path}")
    return df[["code", "name"]].copy() if "name" in df.columns else df[["code"]].copy()


def max_ohlc_date_on_or_before(df: pd.DataFrame | None, run_date: date) -> date | None:
    """
    run_date 以前に収まる行だけを見たときの index の最大日付（営業日バーが run_date まで揃っているかの判定用）。
    index は DatetimeIndex 前提。
    """
    if df is None or df.empty:
        return None
    sub = df[df.index.date <= run_date]
    if sub.empty:
        return None
    return pd.Timestamp(sub.index.max()).date()


def load_stale_exclusions(cache_dir: Path, run_date: date) -> set[str]:
    path = cache_dir / STALE_EXCLUSIONS_FILENAME
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"警告: stale除外ファイルのJSON形式が不正です: {path}", file=sys.stderr)
        return set()
    file_run_date = str(payload.get("run_date") or "").strip()
    if file_run_date != run_date.isoformat():
        print(
            f"警告: stale除外ファイルの run_date が不一致のため無効化します: file={file_run_date}, run_date={run_date.isoformat()}",
            file=sys.stderr,
        )
        return set()
    raw_codes = payload.get("stale_codes")
    if not isinstance(raw_codes, list):
        return set()
    return {str(c).strip() for c in raw_codes if str(c).strip()}


def _init_worker(ctx: dict) -> None:
    global _WORKER_CTX
    _WORKER_CTX = ctx


def _compute_one_code(task: tuple[str, str]) -> dict:
    code, name = task
    run_date: date = _WORKER_CTX["run_date"]
    daily_cache_dir = Path(_WORKER_CTX["daily_cache_dir"])
    z_lookback_days = int(_WORKER_CTX["z_lookback_days"])
    rs_windows: list[int] = list(_WORKER_CTX["rs_windows"])
    benchmarks: dict[str, pd.DataFrame] = _WORKER_CTX["benchmarks"]
    compute_candle = bool(_WORKER_CTX["compute_candle"])

    stock_cache_path = daily_cache_dir / f"{code}.csv"
    stock_df = load_cache(stock_cache_path)
    if stock_df is None or stock_df.empty:
        return {"status": "missing"}
    stock_df = stock_df[stock_df.index.date <= run_date]
    if stock_df.empty:
        return {"status": "missing"}

    latest_idx = stock_df.index.max()
    latest_date = latest_idx.date()
    if latest_date < run_date:
        return {"status": "stale_ohlc", "code": code}

    z_ctx = build_anchor_context(stock_df.index)
    z_turnover = compute_zscore_turnover_from_prepared(
        stock_df,
        z_lookback_days,
        run_date,
        anchor_ctx=z_ctx,
    )
    turnover_ma_ratio = compute_turnover_ma_ratio_from_prepared(
        stock_df,
        z_lookback_days,
        run_date,
        anchor_ctx=z_ctx,
    )
    turnover_yen = stock_df["Close"] * stock_df["Volume"]

    close_series = stock_df["Close"].dropna()
    if len(close_series) >= 2:
        prev_close = float(close_series.iloc[-2])
        cur_close = float(close_series.iloc[-1])
        if prev_close != 0.0 and not (pd.isna(prev_close) or pd.isna(cur_close)):
            price_change_pct = (cur_close / prev_close - 1.0) * 100.0
        else:
            price_change_pct = None
    else:
        price_change_pct = None

    result_row = {
        "date": latest_date.isoformat(),
        "code": code,
        "turnover_yen": turnover_yen.loc[latest_idx] if latest_idx in turnover_yen.index else None,
        f"z_turnover_{z_lookback_days}": z_turnover.iloc[0] if not z_turnover.empty else None,
        f"turnover_ma_ratio_{z_lookback_days}": turnover_ma_ratio.iloc[0] if not turnover_ma_ratio.empty else None,
        "price_change_pct": price_change_pct,
        **build_external_links(code, "link_prefix"),
        "n_bars_used": len(stock_df),
    }
    if name:
        result_row["name"] = name

    if compute_candle and all(col in stock_df.columns for col in ["Open", "High", "Low", "Close"]):
        try:
            if compute_candle_descriptors is None:
                raise RuntimeError("candle descriptor is unavailable")
            candle_labels, price_text = compute_candle_descriptors(stock_df)
            result_row["candle_labels"] = candle_labels
            result_row["price_text"] = price_text
        except Exception:
            result_row["candle_labels"] = None
            result_row["price_text"] = None
    else:
        result_row["candle_labels"] = None
        result_row["price_text"] = None

    nan_count = 0
    if pd.isna(result_row[f"z_turnover_{z_lookback_days}"]):
        nan_count += 1
    if pd.isna(result_row[f"turnover_ma_ratio_{z_lookback_days}"]):
        nan_count += 1
    if pd.isna(result_row["price_change_pct"]):
        nan_count += 1
    for bench_name, bench_df_filtered in benchmarks.items():
        if bench_df_filtered.empty:
            continue
        merged = merged_close(stock_df, bench_df_filtered)
        anchor_ctx = build_anchor_context(merged.index)
        stock_asof = prepare_asof_series(merged["stock_close"])
        bench_asof = prepare_asof_series(merged["bench_close"])

        rs_df = compute_rs_from_merged(
            merged,
            rs_windows,
            run_date,
            anchor_ctx=anchor_ctx,
            stock_asof=stock_asof,
            bench_asof=bench_asof,
        )
        if not rs_df.empty:
            for T in rs_windows:
                col_name = f"rs{T}_{bench_name}"
                value = rs_df.iloc[0][f"rs{T}"]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

        rs_accel = compute_rs_acceleration_from_merged(
            merged,
            run_date,
            short_window=31,
            long_window=252,
            anchor_ctx=anchor_ctx,
            stock_asof=stock_asof,
            bench_asof=bench_asof,
        )
        result_row[f"rs_acceleration_{bench_name}"] = rs_accel.iloc[0] if not rs_accel.empty else None
        if pd.isna(result_row[f"rs_acceleration_{bench_name}"]):
            nan_count += 1

        rs_accel_zscore = compute_rs_acceleration_zscore_from_merged(
            merged,
            run_date,
            lookback_days=z_lookback_days,
            short_window=31,
            long_window=252,
            anchor_ctx=anchor_ctx,
            stock_asof=stock_asof,
            bench_asof=bench_asof,
        )
        result_row[f"rs_acceleration_zscore_{bench_name}"] = (
            rs_accel_zscore.iloc[0] if not rs_accel_zscore.empty else None
        )
        if pd.isna(result_row[f"rs_acceleration_zscore_{bench_name}"]):
            nan_count += 1

        beta_adj_rs = compute_beta_adjusted_rs_from_merged(
            merged,
            run_date,
            beta_window=126,
            return_window=252,
            anchor_ctx=anchor_ctx,
            stock_asof=stock_asof,
            bench_asof=bench_asof,
        )
        result_row[f"beta_adjusted_rs_{bench_name}"] = beta_adj_rs.iloc[0] if not beta_adj_rs.empty else None
        if pd.isna(result_row[f"beta_adjusted_rs_{bench_name}"]):
            nan_count += 1

        info_ratio = compute_information_ratio_from_merged(
            merged,
            run_date,
            window=63,
            anchor_ctx=anchor_ctx,
        )
        result_row[f"information_ratio_{bench_name}"] = info_ratio.iloc[0] if not info_ratio.empty else None
        if pd.isna(result_row[f"information_ratio_{bench_name}"]):
            nan_count += 1

    return {"status": "ok", "row": result_row, "nan_count": nan_count}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compute indicators for equity_domestic_core.")
    parser.add_argument(
        "--input",
        type=str,
        help="equity_domestic_core_with_name.csv のパス（省略時は最新 sets_secondary_YYYYMMDD から自動選択）",
    )
    parser.add_argument(
        "--run-date",
        type=str,
        help="算出対象日（YYYY-MM-DD形式。省略時は今日）",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    daily_cache_dir = get_yf_daily_cache_dir(base)
    index_cache_dir = get_yf_index_cache_dir(base)
    indicators_dir = get_indicators_daily_dir(base)

    input_path: Path | None
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
    assert input_path is not None

    if not input_path.exists():
        print(f"エラー: 入力が存在しません: {input_path}", file=sys.stderr)
        sys.exit(1)

    run_date = parse_run_date_opt(args.run_date) or date.today()

    try:
        codes_df = _load_codes_with_names(input_path)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    z_lookback_days = get_z_lookback_days()
    rs_windows = get_rs_windows()
    rs_benchmark = get_rs_benchmark()
    configured_workers = get_indicators_max_workers()
    max_workers = configured_workers or max(1, (os.cpu_count() or 2) - 1)
    if configured_workers is not None and (configured_workers < 1 or configured_workers > 8):
        print(
            f"警告: INDICATORS_MAX_WORKERS={configured_workers} は推奨範囲(1-8)外です。"
            " 実行環境のCPU/メモリに応じて見直してください。",
            file=sys.stderr,
        )

    print(f"入力: {input_path} 銘柄数={len(codes_df)}", file=sys.stderr)
    print(f"z_lookback_days={z_lookback_days}, rs_windows={rs_windows}, rs_benchmark={rs_benchmark}", file=sys.stderr)
    excluded_by_stale = load_stale_exclusions(daily_cache_dir, run_date)
    if excluded_by_stale:
        preview = sorted(excluded_by_stale)[:40]
        more = "..." if len(excluded_by_stale) > len(preview) else ""
        print(
            f"stale除外ポリシー適用: excluded_by_stale_policy={len(excluded_by_stale)} codes={preview}{more}",
            file=sys.stderr,
        )

    # ベンチマーク読み込み
    benchmarks = {}
    if rs_benchmark in ("TOPIX", "BOTH"):
        topix_path = index_cache_dir / "topix.csv"
        topix_df = load_cache(topix_path)
        if topix_df is not None:
            benchmarks["topix"] = topix_df
        else:
            print(f"警告: TOPIXキャッシュが見つかりません: {topix_path}", file=sys.stderr)
    if rs_benchmark in ("NIKKEI", "BOTH"):
        nikkei_path = index_cache_dir / "nikkei.csv"
        nikkei_df = load_cache(nikkei_path)
        if nikkei_df is not None:
            benchmarks["nikkei"] = nikkei_df
        else:
            print(f"警告: Nikkeiキャッシュが見つかりません: {nikkei_path}", file=sys.stderr)

    if not benchmarks:
        print("エラー: ベンチマークデータが利用できません", file=sys.stderr)
        sys.exit(1)

    # run_date 当日バーまで揃っていないベンチは RS 系が前日と不自然に一致しうるためここで止める（ensure 通過後の最終防衛）
    for bench_name, bench_df in benchmarks.items():
        md = max_ohlc_date_on_or_before(bench_df, run_date)
        if md is not None and md < run_date:
            print(
                f"エラー: ベンチマーク {bench_name} のOHLC最新日({md})が run_date({run_date}) より前です。"
                f" ensure_index_cache またはキャッシュ反映を確認してください。",
                file=sys.stderr,
            )
            sys.exit(2)
    benchmarks_filtered = {
        k: v[v.index.date <= run_date] for k, v in benchmarks.items()
    }
    print(
        f"整合確認: benchmarks={list(benchmarks_filtered.keys())} run_date={run_date.isoformat()}",
        file=sys.stderr,
    )

    # 各銘柄の指標を計算
    started = time.perf_counter()
    results = []
    nan_count = 0
    missing_count = 0
    stale_ohlc_codes: list[str] = []
    tasks: list[tuple[str, str]] = []
    for _, row in codes_df.iterrows():
        code = str(row["code"]).strip()
        if code in excluded_by_stale:
            continue
        tasks.append((code, str(row.get("name", ""))))

    worker_ctx = {
        "run_date": run_date,
        "daily_cache_dir": str(daily_cache_dir),
        "z_lookback_days": z_lookback_days,
        "rs_windows": rs_windows,
        "benchmarks": benchmarks_filtered,
        "compute_candle": compute_candle_descriptors is not None,
    }

    if max_workers <= 1:
        _init_worker(worker_ctx)
        raw_out = [_compute_one_code(t) for t in tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_worker,
            initargs=(worker_ctx,),
        ) as ex:
            raw_out = list(ex.map(_compute_one_code, tasks, chunksize=8))

    for out in raw_out:
        status = out.get("status")
        if status == "missing":
            missing_count += 1
        elif status == "stale_ohlc":
            stale_ohlc_codes.append(str(out.get("code", "")))
        elif status == "ok":
            nan_count += int(out.get("nan_count", 0))
            results.append(out["row"])

    if stale_ohlc_codes:
        preview = stale_ohlc_codes[:40]
        more = "..." if len(stale_ohlc_codes) > len(preview) else ""
        print(
            f"エラー: run_date={run_date.isoformat()} に対し、OHLC 最新日が run_date 未満の銘柄が "
            f"{len(stale_ohlc_codes)} 件あります（例: {preview}{more}）。"
            f" indicators_{run_date.strftime('%Y%m%d')}.csv は出力しません。"
            f" ensure_core_cache の stale 解消・CI の OHLC artifact 受け渡しを確認してください。",
            file=sys.stderr,
        )
        sys.exit(2)

    if not results:
        print("エラー: 計算結果が0件です", file=sys.stderr)
        sys.exit(1)

    elapsed_sec = time.perf_counter() - started
    print(
        f"性能: processed={len(tasks)} workers={max_workers} elapsed_sec={elapsed_sec:.2f}",
        file=sys.stderr,
    )

    # DataFrame化
    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("code").reset_index(drop=True)

    # 出力
    indicators_dir.mkdir(parents=True, exist_ok=True)
    output_path = indicators_dir / f"indicators_{run_date.strftime('%Y%m%d')}.csv"
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"出力: {output_path} ({len(result_df)}行)", file=sys.stderr)

    # サマリ
    # RS指標: len(rs_windows)個 × ベンチマーク数
    # 新規指標: 4個（短期RS加速、短期RS加速zscore、β調整RS、情報比率）× ベンチマーク数
    total_indicators = len(result_df) * (len(rs_windows) + 4) * len(benchmarks)
    nan_ratio = nan_count / total_indicators if total_indicators > 0 else 0
    print(f"サマリ: 計算成功={len(result_df)}, 欠損銘柄={missing_count}, NaN比率={nan_ratio:.2%}", file=sys.stderr)
    if excluded_by_stale:
        print(f"サマリ: excluded_by_stale_policy={len(excluded_by_stale)}", file=sys.stderr)

    if nan_ratio > 0.5:
        print(f"警告: NaN比率が高いです ({nan_ratio:.2%})", file=sys.stderr)

    if missing_count > len(codes_df) * 0.5:
        print(f"警告: 欠損銘柄数が多すぎます ({missing_count}/{len(codes_df)})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
