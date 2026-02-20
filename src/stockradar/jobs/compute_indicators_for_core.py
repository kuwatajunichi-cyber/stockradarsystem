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
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from stockradar.config import (
    get_indicators_daily_dir,
    get_rs_benchmark,
    get_rs_windows,
    get_yf_daily_cache_dir,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.utils.yf_cache import load_cache

# candle_descriptorのインポート（オプション）
try:
    from stockradar.utils.candle_descriptor import compute_candle_descriptors
except ImportError:
    compute_candle_descriptors = None


def _find_latest_core_with_name(base_dir: Path) -> Path | None:
    """data/universe/jpx/sets_secondary_YYYYMMDD/equity_domestic_core_with_name.csv の最新を返す。"""
    jpx_dir = base_dir / "data" / "universe" / "jpx"
    if not jpx_dir.exists():
        return None
    candidates = []
    for d in jpx_dir.iterdir():
        if d.is_dir() and re.match(r"sets_secondary_\d{8}", d.name):
            p = d / "equity_domestic_core_with_name.csv"
            if p.exists():
                candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name)
    return candidates[-1]


def _load_codes_with_names(path: Path) -> pd.DataFrame:
    """code, name列を含むDataFrameを返す。"""
    df = pd.read_csv(path)
    if "code" not in df.columns:
        raise ValueError(f"入力CSVに code 列がありません: {path}")
    return df[["code", "name"]].copy() if "name" in df.columns else df[["code"]].copy()


def _ticker_for_code(code: str) -> str:
    """日本株の Yahoo ティッカー（例: 7203 -> 7203.T）。"""
    return f"{code}.T"


def _build_external_links(code: str) -> dict[str, str]:
    """
    4桁銘柄コードから各サイトへのURLを生成する。
    externalLink_v1.0.md に準拠。
    """
    return {
        "link_kabutan": f"https://kabutan.jp/stock/?code={code}",
        "link_kabutan_chart": f"https://kabutan.jp/stock/chart?code={code}",
        "link_kabutan_news": f"https://kabutan.jp/stock/news?code={code}",
        "link_minkabu": f"https://minkabu.jp/stock/{code}",
        "link_buffett": f"https://www.buffett-code.com/company/{code}",
        "link_yahoo": f"https://finance.yahoo.co.jp/quote/{code}.T",
    }


def compute_zscore_turnover(df: pd.DataFrame, lookback_days: int) -> pd.Series:
    """
    出来高zscore（売買代金近似ベース）を計算。

    Args:
        df: DataFrame（Close, Volume列、date index）
        lookback_days: 窓サイズ（営業日数）

    Returns:
        Series（z_turnover）
    """
    turnover_yen = df["Close"] * df["Volume"]
    log_turnover = np.log1p(turnover_yen)
    min_periods = max(20, int(lookback_days * 0.7))
    z_turnover = (log_turnover - log_turnover.rolling(window=lookback_days, min_periods=min_periods).mean()) / log_turnover.rolling(window=lookback_days, min_periods=min_periods).std()
    return z_turnover


def compute_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    windows: list[int],
) -> pd.DataFrame:
    """
    RS（B方式：期間リターン差）を計算。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        windows: 期間リスト（営業日数）

    Returns:
        DataFrame（rs_T列）
    """
    # 共通営業日で整列（inner join）
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    result = pd.DataFrame(index=merged.index)
    for T in windows:
        stock_ret = merged["stock_close"] / merged["stock_close"].shift(T) - 1
        bench_ret = merged["bench_close"] / merged["bench_close"].shift(T) - 1
        rs_T = stock_ret - bench_ret
        result[f"rs{T}"] = rs_T

    return result


def compute_rs_acceleration(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    short_window: int = 31,
    long_window: int = 252,
) -> pd.Series:
    """
    短期RS加速（Short-term RS Acceleration）を計算。
    短期RSと長期RSの差を算出。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        short_window: 短期窓（営業日数、default=31）
        long_window: 長期窓（営業日数、default=252）

    Returns:
        Series（rs_acceleration）
    """
    # 共通営業日で整列（inner join）
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    # 短期RS
    stock_ret_short = merged["stock_close"] / merged["stock_close"].shift(short_window) - 1
    bench_ret_short = merged["bench_close"] / merged["bench_close"].shift(short_window) - 1
    rs_short = stock_ret_short - bench_ret_short

    # 長期RS
    stock_ret_long = merged["stock_close"] / merged["stock_close"].shift(long_window) - 1
    bench_ret_long = merged["bench_close"] / merged["bench_close"].shift(long_window) - 1
    rs_long = stock_ret_long - bench_ret_long

    # 加速値 = 短期RS - 長期RS
    rs_acceleration = rs_short - rs_long

    return rs_acceleration


def compute_rs_acceleration_zscore(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    lookback_days: int,
    short_window: int = 31,
    long_window: int = 252,
) -> pd.Series:
    """
    短期RS加速のzscoreを計算。
    短期RS加速を標準化窓で標準化した値。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        lookback_days: 標準化窓（営業日数、売買代金zscoreと同じ）
        short_window: 短期窓（営業日数、default=31）
        long_window: 長期窓（営業日数、default=252）

    Returns:
        Series（rs_acceleration_zscore）
    """
    # 短期RS加速を計算
    rs_acceleration = compute_rs_acceleration(stock_df, bench_df, short_window, long_window)

    # zscore化（標準化窓で標準化）
    min_periods = max(20, int(lookback_days * 0.7))
    rs_accel_mean = rs_acceleration.rolling(window=lookback_days, min_periods=min_periods).mean()
    rs_accel_std = rs_acceleration.rolling(window=lookback_days, min_periods=min_periods).std()
    rs_acceleration_zscore = (rs_acceleration - rs_accel_mean) / rs_accel_std

    return rs_acceleration_zscore


def compute_beta_adjusted_rs(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    beta_window: int = 126,
    return_window: int = 252,
) -> pd.Series:
    """
    β調整RS（Market-adjusted Excess Return）を計算。
    βを推定し、市場寄与分を差し引いた純粋な銘柄固有要因の強さを測定。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        beta_window: β推定窓（営業日数、default=126）
        return_window: 累積リターン計算窓（営業日数、default=252）

    Returns:
        Series（beta_adjusted_rs）
    """
    # 共通営業日で整列（inner join）
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    # 日次リターンを計算
    stock_ret = merged["stock_close"].pct_change()
    bench_ret = merged["bench_close"].pct_change()

    # β推定（rolling回帰）
    # 共分散と分散を計算してβを推定
    min_periods = max(20, int(beta_window * 0.7))
    # 2つのSeries間のrolling共分散を計算
    stock_mean = stock_ret.rolling(window=beta_window, min_periods=min_periods).mean()
    bench_mean = bench_ret.rolling(window=beta_window, min_periods=min_periods).mean()
    cov = ((stock_ret - stock_mean) * (bench_ret - bench_mean)).rolling(window=beta_window, min_periods=min_periods).mean()
    bench_var = bench_ret.rolling(window=beta_window, min_periods=min_periods).var()
    beta = cov / bench_var

    # 累積リターン（return_window期間）
    stock_cumret = merged["stock_close"] / merged["stock_close"].shift(return_window) - 1
    bench_cumret = merged["bench_close"] / merged["bench_close"].shift(return_window) - 1

    # 市場寄与分 = β × 市場リターン
    # return_window期間の累積リターンを計算する際に、その期間の開始時点（return_window日前）でのβを使う
    beta_at_start = beta.shift(return_window)
    market_contribution = beta_at_start * bench_cumret

    # β調整RS = 銘柄累積リターン - 市場寄与分
    beta_adjusted_rs = stock_cumret - market_contribution

    return beta_adjusted_rs


def compute_information_ratio(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    window: int = 63,
) -> pd.Series:
    """
    情報比率（Information Ratio）を計算。
    日次超過リターンの平均を標準偏差で割った値。

    Args:
        stock_df: 銘柄DataFrame（Close列、date index）
        bench_df: ベンチマークDataFrame（Close列、date index）
        window: 情報比率窓（営業日数、default=63）

    Returns:
        Series（information_ratio）
    """
    # 共通営業日で整列（inner join）
    merged = pd.merge(
        stock_df[["Close"]].rename(columns={"Close": "stock_close"}),
        bench_df[["Close"]].rename(columns={"Close": "bench_close"}),
        left_index=True,
        right_index=True,
        how="inner",
    )

    # 日次リターンを計算
    stock_ret = merged["stock_close"].pct_change()
    bench_ret = merged["bench_close"].pct_change()

    # 日次超過リターン
    excess_ret = stock_ret - bench_ret

    # 情報比率 = 平均超過リターン / 超過リターンの標準偏差
    min_periods = max(20, int(window * 0.7))
    mean_excess = excess_ret.rolling(window=window, min_periods=min_periods).mean()
    std_excess = excess_ret.rolling(window=window, min_periods=min_periods).std()

    # 標準偏差が0の場合はNaNを返す
    information_ratio = mean_excess / std_excess

    return information_ratio


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
        input_path = _find_latest_core_with_name(base)
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

    if args.run_date:
        try:
            run_date = date.fromisoformat(args.run_date)
        except ValueError:
            print(f"エラー: 日付形式が不正です: {args.run_date} (期待: YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
    else:
        run_date = date.today()

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

    # 各銘柄の指標を計算
    results = []
    nan_count = 0
    missing_count = 0

    for _, row in codes_df.iterrows():
        code = str(row["code"]).strip()
        name = row.get("name", "")

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
        z_turnover = compute_zscore_turnover(stock_df, z_lookback_days)
        turnover_yen = stock_df["Close"] * stock_df["Volume"]

        # 最新日の値を取得（run_dateでフィルタ後の最新日）
        latest_idx = stock_df.index.max()
        latest_date = stock_df.index.max().date()
        
        # dateフィールドはrun_dateを使用（ワークフローで指定された日付）
        # 指標の値はlatest_idx（実際のデータがある最新日）から取得
        if latest_date < run_date:
            print(f"警告: {code} の最新データ日付({latest_date})がrun_date({run_date})より古いです", file=sys.stderr)
        
        result_row = {
            "date": run_date.isoformat(),  # run_dateを使用（ワークフローで指定された日付）
            "code": code,
            "turnover_yen": turnover_yen.loc[latest_idx] if latest_idx in turnover_yen.index else None,
            f"z_turnover_{z_lookback_days}": z_turnover.loc[latest_idx] if latest_idx in z_turnover.index else None,
            **_build_external_links(code),
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
            rs_df = compute_rs(stock_df, bench_df_filtered, rs_windows)
            if not rs_df.empty and latest_idx in rs_df.index:
                for T in rs_windows:
                    col_name = f"rs{T}_{bench_name}"
                    value = rs_df.loc[latest_idx, f"rs{T}"]
                    result_row[col_name] = value
                    if pd.isna(value):
                        nan_count += 1

            # 短期RS加速（Short-term RS Acceleration）
            rs_accel = compute_rs_acceleration(stock_df, bench_df_filtered, short_window=31, long_window=252)
            if not rs_accel.empty and latest_idx in rs_accel.index:
                col_name = f"rs_acceleration_{bench_name}"
                value = rs_accel.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # 短期RS加速のzscore
            rs_accel_zscore = compute_rs_acceleration_zscore(
                stock_df, bench_df_filtered, lookback_days=z_lookback_days, short_window=31, long_window=252
            )
            if not rs_accel_zscore.empty and latest_idx in rs_accel_zscore.index:
                col_name = f"rs_acceleration_zscore_{bench_name}"
                value = rs_accel_zscore.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # β調整RS（Market-adjusted Excess Return）
            beta_adj_rs = compute_beta_adjusted_rs(stock_df, bench_df_filtered, beta_window=126, return_window=252)
            if not beta_adj_rs.empty and latest_idx in beta_adj_rs.index:
                col_name = f"beta_adjusted_rs_{bench_name}"
                value = beta_adj_rs.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

            # 情報比率（Information Ratio）
            info_ratio = compute_information_ratio(stock_df, bench_df_filtered, window=63)
            if not info_ratio.empty and latest_idx in info_ratio.index:
                col_name = f"information_ratio_{bench_name}"
                value = info_ratio.loc[latest_idx]
                result_row[col_name] = value
                if pd.isna(value):
                    nan_count += 1

        # n_bars_used（監査用）
        result_row["n_bars_used"] = len(stock_df)

        results.append(result_row)

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

    if nan_ratio > 0.5:
        print(f"警告: NaN比率が高いです ({nan_ratio:.2%})", file=sys.stderr)

    if missing_count > len(codes_df) * 0.5:
        print(f"警告: 欠損銘柄数が多すぎます ({missing_count}/{len(codes_df)})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
