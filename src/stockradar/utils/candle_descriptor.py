"""
ローソク足の特徴量計算とラベル生成（OHLC descriptor）。

ドキュメント: docs/OHLC_desripter_v1.1.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# JPX制限値幅テーブル（基準値段 -> 制限値幅）
JPX_LIMIT_TABLE = [
    (100, 30),
    (200, 50),
    (500, 80),
    (700, 100),
    (1000, 150),
    (1500, 300),
    (2000, 400),
    (3000, 500),
    (5000, 700),
    (7000, 1000),
    (10000, 1500),
    (15000, 3000),
    (20000, 4000),
    (30000, 5000),
    (50000, 7000),
    (70000, 10000),
    (100000, 15000),
    (150000, 30000),
    (200000, 40000),
    (300000, 50000),
    (500000, 70000),
    (700000, 100000),
    (1000000, 150000),
    (1500000, 300000),
    (2000000, 400000),
    (3000000, 500000),
    (5000000, 700000),
    (7000000, 1000000),
    (10000000, 1500000),
    (15000000, 3000000),
    (20000000, 4000000),
    (30000000, 5000000),
    (50000000, 7000000),
    (float("inf"), 10000000),  # 50,000,000円以上
]


def get_limit_range(prev_close: float) -> float:
    """
    前日終値から制限値幅を取得。

    Args:
        prev_close: 前日終値

    Returns:
        制限値幅（円）
    """
    for threshold, limit_range in JPX_LIMIT_TABLE:
        if prev_close < threshold:
            return limit_range
    return 10000000  # フォールバック


def compute_true_range(df: pd.DataFrame, prev_close: pd.Series | None = None) -> pd.Series:
    """
    True Range (TR)を計算。

    Args:
        df: DataFrame（Open, High, Low, Close列、date index）
        prev_close: 前日終値のSeries（indexはdfのindexより1日ずれている想定）

    Returns:
        Series（TR）
    """
    h_l = df["High"] - df["Low"]
    if prev_close is not None:
        # prev_closeのindexを1日進めてdfと揃える
        prev_close_aligned = prev_close.shift(-1).reindex(df.index, method="ffill")
        h_prevc = abs(df["High"] - prev_close_aligned)
        l_prevc = abs(df["Low"] - prev_close_aligned)
        tr = pd.concat([h_l, h_prevc, l_prevc], axis=1).max(axis=1)
    else:
        tr = h_l
    return tr


def compute_candle_features(df: pd.DataFrame, prev_close: pd.Series | None = None) -> pd.DataFrame:
    """
    ローソク足の特徴量を計算。

    Args:
        df: DataFrame（Open, High, Low, Close列、date index）
        prev_close: 前日終値のSeries

    Returns:
        DataFrame（追加列: TR, B, U, D, dir, br, ur, dr, gap, gap_atr, gap_dir, close_pos, hit_high, hit_low）
    """
    result = df.copy()

    # True Range
    result["TR"] = compute_true_range(df, prev_close)

    # ローソク基本量
    result["B"] = abs(df["Close"] - df["Open"])  # 実体
    result["U"] = df["High"] - pd.concat([df["Open"], df["Close"]], axis=1).max(axis=1)  # 上ヒゲ
    result["D"] = pd.concat([df["Open"], df["Close"]], axis=1).min(axis=1) - df["Low"]  # 下ヒゲ
    result["dir"] = np.sign(df["Close"] - df["Open"])  # 陽/陰/同値

    # 比率
    result["br"] = result["B"] / result["TR"].replace(0, np.nan)  # 実体比率
    result["ur"] = result["U"] / result["TR"].replace(0, np.nan)  # 上ヒゲ比率
    result["dr"] = result["D"] / result["TR"].replace(0, np.nan)  # 下ヒゲ比率

    # ギャップ
    if prev_close is not None:
        prev_close_aligned = prev_close.shift(-1).reindex(df.index, method="ffill")
        result["gap"] = df["Open"] - prev_close_aligned
    else:
        result["gap"] = np.nan

    # close_pos, hit_high, hit_low
    h_l_diff = df["High"] - df["Low"]
    result["close_pos"] = (df["Close"] - df["Low"]) / h_l_diff.replace(0, np.nan)
    result["hit_high"] = (df["Close"] == df["High"]).astype(int)
    result["hit_low"] = (df["Close"] == df["Low"]).astype(int)

    return result


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR (Average True Range)を計算（EMA）。

    Args:
        df: DataFrame（TR列、date index）
        period: EMA期間（default=14）

    Returns:
        Series（ATR）
    """
    return df["TR"].ewm(span=period, adjust=False).mean()


def compute_percentile_rank(series: pd.Series, window: int = 252) -> pd.Series:
    """
    Percentile rankを計算。

    Args:
        series: Series
        window: 窓サイズ（default=252）

    Returns:
        Series（percentile_rank, 0-1）
    """
    return series.rolling(window=window, min_periods=min(20, window // 4)).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else np.nan, raw=False
    )


def compute_limit_suspect_labels(
    df: pd.DataFrame,
    prev_close: float,
) -> str | None:
    """
    制限値幅テーブルを使った制限付き値幅の疑いラベルを判定。

    Args:
        df: DataFrame（Open, High, Low, Close列、最新日のみ）
        prev_close: 前日終値

    Returns:
        ラベル文字列（該当なしの場合はNone）
    """
    if len(df) == 0:
        return None

    latest = df.iloc[-1]
    o = latest["Open"]
    h = latest["High"]
    l = latest["Low"]
    c = latest["Close"]

    # 制限値幅を取得
    limit_range = get_limit_range(prev_close)
    limit_high = prev_close + limit_range
    limit_low = prev_close - limit_range

    # 高値・安値に到達したか
    hit_limit_high = h >= limit_high
    hit_limit_low = l <= limit_low

    # 優先順位の逆順（下から順）にチェック（最後に見つかったものが優先）
    label = None

    # 1. Hが高値に到達：S高タッチ疑い
    if hit_limit_high:
        label = "LIMIT_HIGH_TOUCH"

    # 2. Lが安値に到達：S安タッチ疑い
    if hit_limit_low:
        label = "LIMIT_LOW_TOUCH"

    # 3. Hが高値に到達し、Cも同値：S高タッチ後張付き疑い
    if hit_limit_high and c >= limit_high:
        label = "LIMIT_HIGH_TOUCH_STUCK"

    # 4. Lが安値に到達し、Cも同値：S安タッチ後張付き疑い
    if hit_limit_low and c <= limit_low:
        label = "LIMIT_LOW_TOUCH_STUCK"

    # 5. Hが高値に到達し、Oも同値、しかしCは到達しない：S高寄天疑い
    if hit_limit_high and o >= limit_high and c < limit_high:
        label = "LIMIT_HIGH_OPEN_ONLY"

    # 6. Lが安値に到達し、Oも同値、しかしCは到達しない：S安寄底疑い
    if hit_limit_low and o <= limit_low and c > limit_low:
        label = "LIMIT_LOW_OPEN_ONLY"

    # 7. OHLC全て高値に到達：S高完全張り付き疑い
    # H, O, Cが制限高値に到達し、Lも制限高値に到達（実質的に全てが制限高値）
    if h >= limit_high and o >= limit_high and c >= limit_high and l >= limit_high:
        label = "LIMIT_HIGH_FULL_STUCK"

    # 8. OHLC全て安値に到達：S安完全張り付き疑い
    # H, O, Cが制限安値に到達し、Hも制限安値に到達（実質的に全てが制限安値）
    if h <= limit_low and o <= limit_low and c <= limit_low and l <= limit_low:
        label = "LIMIT_LOW_FULL_STUCK"

    return label


def compute_candle_labels(
    df: pd.DataFrame,
    atr: pd.Series,
    q_sr: pd.Series,
    gap_atr: pd.Series,
    prev_close: float | None = None,
) -> str:
    """
    ローソク足のラベルを計算。

    Args:
        df: DataFrame（特徴量計算済み）
        atr: ATR Series
        q_sr: percentile_rank of sr Series
        gap_atr: gap_atr Series

    Returns:
        Series（ラベル文字列、カンマ区切り）
    """
    labels_list = []

    # 最新日の値を取得
    latest_idx = df.index[-1] if len(df) > 0 else None
    if latest_idx is None:
        return ""

    latest_tr = df.loc[latest_idx, "TR"]
    latest_atr_val = atr.loc[latest_idx] if latest_idx in atr.index else np.nan
    latest_gap_atr_val = gap_atr.loc[latest_idx] if latest_idx in gap_atr.index else np.nan
    latest_gap = df.loc[latest_idx, "gap"]
    latest_hit_high = df.loc[latest_idx, "hit_high"]
    latest_hit_low = df.loc[latest_idx, "hit_low"]
    latest_close_pos = df.loc[latest_idx, "close_pos"]
    latest_open = df.loc[latest_idx, "Open"]

    # 制限値幅テーブルを使った判定（S高・S安はレンジ0より優先）
    limit_label = None
    if prev_close is not None and not pd.isna(prev_close):
        limit_label = compute_limit_suspect_labels(df, prev_close)
        if limit_label:
            labels_list.append(limit_label)

    # 異常ラベル（優先。ただし制限値幅ラベルが既にある場合はスキップ）
    if latest_tr == 0 and limit_label is None:
        labels_list.append("INVALID_TR0")

    # INVALID_NANの出力はOFF（一旦無効化）
    # if pd.isna(latest_atr_val) or latest_atr_val <= 0:
    #     labels_list.append("INVALID_NAN")

    # ACTION_SUSPECT
    if not pd.isna(latest_gap_atr_val):
        prev_close_approx = latest_open - latest_gap
        if latest_gap_atr_val >= 5 or (
            not pd.isna(prev_close_approx) and prev_close_approx != 0 and abs(latest_gap / prev_close_approx) >= 0.30
        ):
            labels_list.append("ACTION_SUSPECT")

    # GAP_DOMINANT
    if not pd.isna(latest_gap_atr_val) and latest_gap_atr_val >= 1.0:
        if latest_tr > 0 and abs(latest_gap) / latest_tr >= 0.6:
            labels_list.append("GAP_DOMINANT")

    # GAP_UP / GAP_DOWN（窓ラベル）はcompute_candle_descriptorsで判定（前日データが必要なため）

    # サイズラベル
    if isinstance(q_sr, pd.Series):
        q_sr_val = q_sr.iloc[-1] if len(q_sr) > 0 else np.nan
    else:
        q_sr_val = q_sr

    if not pd.isna(q_sr_val):
        if q_sr_val >= 0.95:
            labels_list.append("RANGE_VERY_LARGE")
        elif q_sr_val >= 0.85:
            labels_list.append("RANGE_LARGE")
        elif q_sr_val < 0.40:
            if q_sr_val < 0.15:
                labels_list.append("RANGE_VERY_SMALL")
            else:
                labels_list.append("RANGE_SMALL")

    # 形状ラベル（実体）
    br_val = df["br"].iloc[-1] if len(df) > 0 else np.nan
    if not pd.isna(br_val):
        if br_val <= 0.10:
            labels_list.append("DOJI")
        elif br_val >= 0.70:
            ur_val = df["ur"].iloc[-1] if len(df) > 0 else np.nan
            dr_val = df["dr"].iloc[-1] if len(df) > 0 else np.nan
            if not pd.isna(ur_val) and not pd.isna(dr_val):
                if max(ur_val, dr_val) <= 0.15:
                    labels_list.append("BODY_MARUBOZU_LIKE")
        elif br_val >= 0.55:
            labels_list.append("BODY_LONG")
        elif br_val <= 0.25:
            labels_list.append("BODY_SMALL")
        else:
            labels_list.append("BODY_MIDDLE")

    # ヒゲラベル
    ur_val = df["ur"].iloc[-1] if len(df) > 0 else np.nan
    dr_val = df["dr"].iloc[-1] if len(df) > 0 else np.nan
    if not pd.isna(ur_val) and not pd.isna(dr_val):
        if ur_val >= 0.45 and dr_val >= 0.45:
            labels_list.append("WICK_BOTH_LONG")
        elif ur_val >= 0.25 and dr_val >= 0.25:
            labels_list.append("WICK_BOTH_PRESENT")
        elif ur_val >= 0.45:
            labels_list.append("WICK_UPPER_LONG")
        elif dr_val >= 0.45:
            labels_list.append("WICK_LOWER_LONG")
        elif ur_val >= 0.25:
            labels_list.append("WICK_UPPER_PRESENT")
        elif dr_val >= 0.25:
            labels_list.append("WICK_LOWER_PRESENT")

    # 方向ラベル
    dir_val = df["dir"].iloc[-1] if len(df) > 0 else 0
    if "DOJI" not in labels_list:
        if dir_val > 0:
            labels_list.append("DIR_BULL")
        elif dir_val < 0:
            labels_list.append("DIR_BEAR")

    return ",".join(labels_list) if labels_list else ""


def compute_price_text(df: pd.DataFrame, labels: str, q_sr: float | pd.Series) -> str:
    """
    価格挙動の自然言語テキストを生成。

    Args:
        df: DataFrame（特徴量計算済み）
        labels: ラベル文字列（カンマ区切り）
        q_sr: percentile_rank値

    Returns:
        価格挙動の説明文
    """
    label_set = set(labels.split(",")) if labels else set()
    parts = []

    # 制限値幅ラベル（S高・S安はレンジ0より優先）
    # 優先順位の逆順（下から順）にチェック（最後に見つかったものが優先）
    limit_text = None
    if "LIMIT_LOW_FULL_STUCK" in label_set:
        limit_text = "S安完全張り付き疑い"
    if "LIMIT_HIGH_FULL_STUCK" in label_set:
        limit_text = "S高完全張り付き疑い"
    if "LIMIT_LOW_OPEN_ONLY" in label_set:
        limit_text = "S安寄底疑い"
    if "LIMIT_HIGH_OPEN_ONLY" in label_set:
        limit_text = "S高寄天疑い"
    if "LIMIT_LOW_TOUCH_STUCK" in label_set:
        limit_text = "S安タッチ後張付き疑い"
    if "LIMIT_HIGH_TOUCH_STUCK" in label_set:
        limit_text = "S高タッチ後張付き疑い"
    if "LIMIT_LOW_TOUCH" in label_set:
        limit_text = "S安タッチ疑い"
    if "LIMIT_HIGH_TOUCH" in label_set:
        limit_text = "S高タッチ疑い"
    
    if limit_text:
        return limit_text

    # 異常ラベル（優先。ただし制限値幅ラベルが既にある場合はスキップ）
    if "INVALID_TR0" in label_set:
        return "レンジ0"
    if "INVALID_NAN" in label_set:
        return "判定不能"
    if "ACTION_SUSPECT" in label_set:
        return "構造要因疑い"
    if "SPLIT_CONFIRMED" in label_set:
        return "分割明示"
    if "GAP_DOMINANT" in label_set:
        parts.append("ギャップ主導")

    # 窓（先頭）
    if "GAP_UP" in label_set:
        parts.append("上窓つき")
    elif "GAP_DOWN" in label_set:
        parts.append("下窓つき")

    # サイズ（RANGE_NORMALは表示しない）
    if "RANGE_VERY_LARGE" in label_set:
        parts.append("極大の")
    elif "RANGE_LARGE" in label_set:
        parts.append("大きな")
    elif "RANGE_SMALL" in label_set:
        parts.append("小さな")
    elif "RANGE_VERY_SMALL" in label_set:
        parts.append("極小の")

    # ヒゲ
    if "WICK_BOTH_LONG" in label_set:
        parts.append("長い上下ヒゲ")
    elif "WICK_BOTH_PRESENT" in label_set:
        parts.append("上下ヒゲ")
    elif "WICK_UPPER_LONG" in label_set:
        parts.append("長い上ヒゲ")
    elif "WICK_LOWER_LONG" in label_set:
        parts.append("長い下ヒゲ")
    elif "WICK_UPPER_PRESENT" in label_set:
        parts.append("上ヒゲ")
    elif "WICK_LOWER_PRESENT" in label_set:
        parts.append("下ヒゲ")

    # 実体
    if "DOJI" in label_set:
        parts.append("十字線")
    elif "BODY_MARUBOZU_LIKE" in label_set:
        parts.append("丸坊主")
    elif "BODY_LONG" in label_set:
        parts.append("長")
    elif "BODY_SMALL" in label_set:
        parts.append("短")
    elif "BODY_MIDDLE" in label_set:
        parts.append("中")

    # 方向（DOJIの場合は付けない）
    if "DOJI" not in label_set:
        if "DIR_BULL" in label_set:
            parts.append("陽線")
        elif "DIR_BEAR" in label_set:
            parts.append("陰線")

    return "".join(parts) if parts else ""


def compute_candle_descriptors(
    df: pd.DataFrame,
    atr_period: int = 14,
    percentile_window: int = 252,
) -> tuple[str, str]:
    """
    ローソク足のラベルと価格テキストを計算。

    基準となるATRは「前日まで」の系列で計算し、当日の gap_atr・sr は前日時点のATRで
    正規化する。これにより窓（GAP_UP/GAP_DOWN）とサイズ（RANGE_*）の判定が明確になる。

    Args:
        df: DataFrame（Open, High, Low, Close列、date index）
        atr_period: ATR計算期間（default=14）
        percentile_window: percentile_rank計算窓（default=252）

    Returns:
        (candle_labels, price_text)
    """
    if df.empty or len(df) < 2:
        return "", ""

    # 前日終値を取得
    prev_close = df["Close"].shift(1)

    # 特徴量計算
    features_df = compute_candle_features(df, prev_close)

    # ATR計算（当日のTRを含めた系列）
    atr_raw = compute_atr(features_df, period=atr_period)
    # 基準ATRを「前日まで」とする: 各日付で前日時点のATRを使用（窓・サイズの判定が明確になる）
    atr = atr_raw.shift(1)

    # percentile_rank計算（sr = 当日TR / 前日までのATR）
    sr = features_df["TR"] / atr.replace(0, np.nan)
    q_sr = compute_percentile_rank(sr, window=percentile_window)

    # gap_atr計算（当日ギャップを前日までのATRで正規化）
    gap_atr = abs(features_df["gap"]) / atr.replace(0, np.nan)

    # 最新日の値を取得
    latest_features = features_df.iloc[-1]
    latest_atr = atr.iloc[-1] if len(atr) > 0 else np.nan
    latest_q_sr = q_sr.iloc[-1] if len(q_sr) > 0 else np.nan
    latest_gap_atr = gap_atr.iloc[-1] if len(gap_atr) > 0 else np.nan

    # 前日終値を取得（最新日の前日終値）
    latest_prev_close = None
    if len(df) >= 2:
        latest_prev_close = df["Close"].iloc[-2]

    # ラベル計算（最新日のみ）
    # indexを日付に揃える（atr/gap_atrとの.loc照合で異常ラベル判定が正しく動くため）
    latest_df = pd.DataFrame([latest_features], index=[features_df.index[-1]])
    latest_atr_series = pd.Series([latest_atr], index=[features_df.index[-1]])
    latest_q_sr_series = pd.Series([latest_q_sr], index=[features_df.index[-1]])
    latest_gap_atr_series = pd.Series([latest_gap_atr], index=[features_df.index[-1]])
    labels = compute_candle_labels(
        latest_df, latest_atr_series, latest_q_sr_series, latest_gap_atr_series, latest_prev_close
    )

    # 窓ラベルの判定（前日データが必要なため、ここで判定）
    if len(df) >= 2:
        # 前日と当日のデータを取得
        prev_row = df.iloc[-2]  # 前日
        today_row = df.iloc[-1]  # 当日
        
        prev_high = prev_row["High"]
        prev_low = prev_row["Low"]
        today_high = today_row["High"]
        today_low = today_row["Low"]
        
        # 前日の最高値 < 当日の最低値 → 下窓つき（ユーザー指定）
        if prev_high < today_low:
            if "GAP_DOWN" not in labels.split(","):
                labels = labels + ",GAP_DOWN" if labels else "GAP_DOWN"
        # 前日の最低値 > 当日の最高値 → 上窓つき（ユーザー指定）
        elif prev_low > today_high:
            if "GAP_UP" not in labels.split(","):
                labels = labels + ",GAP_UP" if labels else "GAP_UP"

    # price_text生成
    price_text = compute_price_text(latest_df, labels, latest_q_sr)

    return labels, price_text
