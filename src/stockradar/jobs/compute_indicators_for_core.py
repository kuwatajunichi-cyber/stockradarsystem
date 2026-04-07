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
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.config import (
    get_indicators_daily_dir,
    get_rs_benchmark,
    get_rs_windows,
    get_yf_daily_cache_dir,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.indicators import (
    compute_beta_adjusted_rs,
    compute_information_ratio,
    compute_rs,
    compute_rs_acceleration,
    compute_rs_acceleration_zscore,
    compute_zscore_turnover,
)
from stockradar.utils.external_links import build_external_links
from stockradar.utils.paths import (
    PATTERN_SETS_SECONDARY,
    find_latest_matching,
    get_universe_jpx_dir,
)
from stockradar.utils.yf_cache import load_cache

STALE_EXCLUSIONS_FILENAME = "_stale_exclusions.json"

# candle_descriptorのインポート（オプション）
try:
    from stockradar.utils.candle_descriptor import compute_candle_descriptors
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

    run_date = parse_run_date_opt(args.run_date) or date.today()

    try:
        codes_df = _load_codes_with_names(input_path)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    z_lookback_days = get_z_lookback_days()
    rs_windows = get_rs_windows()
    rs_benchmark = get_rs_benchmark()

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

    # 各銘柄の指標を計算
    results = []
    nan_count = 0
    missing_count = 0
    stale_ohlc_codes: list[str] = []

    for _, row in codes_df.iterrows():
        code = str(row["code"]).strip()
        name = row.get("name", "")
        if code in excluded_by_stale:
            continue

        # 銘柄データ読み込み
        stock_cache_path = daily_cache_dir / f"{code}.csv"
        stock_df = load_cache(stock_cache_path)
        if stock_df is None or stock_df.empty:
            missing_count += 1
            continue

        # run_dateでフィルタ
        stock_df = stock_df[stock_df.index.date <= run_date]
        if stock_df.empty:
            missing_count += 1
            continue

        # 出来高zscore計算
        z_turnover = compute_zscore_turnover(stock_df, z_lookback_days, run_date)
        turnover_yen = stock_df["Close"] * stock_df["Volume"]

        # 最新日の値を取得（run_dateでフィルタ後の最新日）
        latest_idx = stock_df.index.max()
        latest_date = stock_df.index.max().date()

        # run_date 名義の日次 job では当日バー未達のまま出力すると前営業日と全行一致する事故になるため、行を出さず失敗扱いに集約する
        if latest_date < run_date:
            stale_ohlc_codes.append(code)
            continue

        result_row = {
            "date": latest_date.isoformat(),  # latest_idx（実データ最新日）を使用
            "code": code,
            "turnover_yen": turnover_yen.loc[latest_idx] if latest_idx in turnover_yen.index else None,
            f"z_turnover_{z_lookback_days}": z_turnover.loc[latest_idx] if latest_idx in z_turnover.index else None,
            **build_external_links(code, "link_prefix"),
        }
        if "name" in codes_df.columns:
            result_row["name"] = name

        # candle_labelsとprice_textを計算（Open, High, Lowが必要）
        if compute_candle_descriptors is not None and all(col in stock_df.columns for col in ["Open", "High", "Low", "Close"]):
            try:
                candle_labels, price_text = compute_candle_descriptors(stock_df)
                result_row["candle_labels"] = candle_labels
                result_row["price_text"] = price_text
            except Exception as e:
                print(f"警告: {code} のcandle descriptor計算に失敗: {type(e).__name__}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                result_row["candle_labels"] = None
                result_row["price_text"] = None
        else:
            # Open, High, Lowが無い場合、またはインポート失敗時はスキップ
            result_row["candle_labels"] = None
            result_row["price_text"] = None

        # RS計算
        for bench_name, bench_df in benchmarks.items():
            bench_df_filtered = bench_df[bench_df.index.date <= run_date]
            if bench_df_filtered.empty:
                continue
            rs_df = compute_rs(stock_df, bench_df_filtered, rs_windows, run_date)
            if not rs_df.empty and latest_idx in rs_df.index:
                for T in rs_windows:
                    col_name = f"rs{T}_{bench_name}"
                    value = rs_df.loc[latest_idx, f"rs{T}"]
                    result_row[col_name] = value
                    if pd.isna(value):
                        nan_count += 1

            # 短期RS加速（Short-term RS Acceleration）
            rs_accel = compute_rs_acceleration(
                stock_df,
                bench_df_filtered,
                run_date,
                short_window=31,
                long_window=252,
            )
            if not rs_accel.empty and latest_idx in rs_accel.index:
                col_name = f"rs_acceleration_{bench_name}"
                value = rs_accel.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # 短期RS加速のzscore
            rs_accel_zscore = compute_rs_acceleration_zscore(
                stock_df,
                bench_df_filtered,
                run_date,
                lookback_days=z_lookback_days,
                short_window=31,
                long_window=252,
            )
            if not rs_accel_zscore.empty and latest_idx in rs_accel_zscore.index:
                col_name = f"rs_acceleration_zscore_{bench_name}"
                value = rs_accel_zscore.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # β調整RS（Market-adjusted Excess Return）
            beta_adj_rs = compute_beta_adjusted_rs(
                stock_df,
                bench_df_filtered,
                run_date,
                beta_window=126,
                return_window=252,
            )
            if not beta_adj_rs.empty and latest_idx in beta_adj_rs.index:
                col_name = f"beta_adjusted_rs_{bench_name}"
                value = beta_adj_rs.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # 情報比率（Information Ratio）
            info_ratio = compute_information_ratio(
                stock_df,
                bench_df_filtered,
                run_date,
                window=63,
            )
            if not info_ratio.empty and latest_idx in info_ratio.index:
                col_name = f"information_ratio_{bench_name}"
                value = info_ratio.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

        # n_bars_used（監査用）
        result_row["n_bars_used"] = len(stock_df)

        results.append(result_row)

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

    # DataFrame化
    result_df = pd.DataFrame(results)

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
