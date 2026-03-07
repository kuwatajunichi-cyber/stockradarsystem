"""
yfinance取得ラッパとキャッシュI/Oの共通コンポーネント。

- 分割取得、sleep、retry、merge、barsカウント
- cache I/O（銘柄別csv、manifest jsonl）
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from stockradar.config import (
    get_yf_retry_backoff_sec,
    get_yf_retry_max,
    get_yf_sleep_sec_between_batches,
)

MANIFEST_FILENAME = "_manifest.jsonl"


def period_for_required_days(required_days: int) -> str:
    """
    required_days 営業日を満たす period 文字列。
    1年では東証休日により約245営業日程度しか返らないため、
    required_days が 252 のときも 2年分を要求する。
    """
    if required_days <= 126:
        return "6mo"
    if required_days <= 252:
        return "2y"  # 1y だと約245営業日で不足するため 2y で余裕を持たせる
    return "2y"


def start_end_for_required_days(required_days: int) -> tuple[datetime, datetime]:
    """required_days 営業日をカバーする calendar 日範囲（余裕多め）。"""
    end = datetime.now(timezone.utc)
    # 営業日 252 日 ≈ 約 1 年、余裕で 400 日
    days_back = min(400, max(365, required_days * 2))
    start = end - timedelta(days=days_back)
    return start, end


def load_cache(cache_path: Path) -> pd.DataFrame | None:
    """
    キャッシュCSVを読み込む。

    Returns:
        DataFrame（date列をindexに設定済み）またはNone（ファイルなし）
    """
    if not cache_path.exists():
        return None
    try:
        df = pd.read_csv(cache_path, encoding="utf-8-sig", index_col=0)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def save_cache(cache_path: Path, df: pd.DataFrame) -> None:
    """キャッシュCSVを保存。"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, encoding="utf-8-sig")


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    """manifest を読んで symbol -> 最終エントリの辞書を返す。"""
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
                symbol = ent.get("symbol") or ent.get("code")  # 後方互換性
                if symbol:
                    out[symbol] = ent
            except json.JSONDecodeError:
                continue
    return out


def update_manifest(manifest_path: Path, entries: dict[str, dict]) -> None:
    """manifest全体を書き直す。"""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        for symbol in sorted(entries):
            f.write(json.dumps(entries[symbol], ensure_ascii=False) + "\n")


def fetch_yf_data(
    ticker: str,
    required_days: int,
    run_date: date | None = None,
    start_date: date | None = None,
    retry_max: int | None = None,
    backoff_sec: list[int] | None = None,
) -> pd.DataFrame | None:
    """
    1ティッカー分のyfinanceデータを取得。

    Args:
        ticker: ティッカー（例: "7203.T", "1306.T"）
        required_days: 必要な営業日数
        run_date: 取得終了日（None時は今日）
        start_date: 取得開始日（None時はrequired_daysから自動計算、差分取得時に指定）
        retry_max: 最大再試行回数（None時はconfigから取得）
        backoff_sec: 再試行待機秒リスト（None時はconfigから取得）

    Returns:
        DataFrame（Close, Volume列、date index）またはNone（取得失敗）
    """
    if retry_max is None:
        retry_max = get_yf_retry_max()
    if backoff_sec is None:
        backoff_sec = get_yf_retry_backoff_sec()

    end_dt = datetime.now(timezone.utc)
    if run_date:
        # yfinanceのendパラメータはexclusive（含まない）のため、run_dateのデータを含めるには+1日する必要がある
        end_date = run_date + timedelta(days=1)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # start_dateが指定されている場合は差分取得モード
    if start_date:
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        # 差分取得時はstart/endのみを使用（periodは使わない）
        use_period = False
    else:
        # フル取得時は従来通り
        period = period_for_required_days(required_days)
        start_dt, _ = start_end_for_required_days(required_days)
        use_period = True

    last_error: str | None = None
    for attempt in range(retry_max + 1):
        try:
            t = yf.Ticker(ticker)
            if use_period:
                hist = t.history(period=period, interval="1d", auto_adjust=True)
                # 日本株等で period が空になることがあるため、start/end で再試行
                if hist is None or hist.empty:
                    hist = t.history(
                        start=start_dt.strftime("%Y-%m-%d"),
                        end=end_dt.strftime("%Y-%m-%d"),
                        interval="1d",
                        auto_adjust=True,
                    )
            else:
                # 差分取得時はstart/endのみを使用
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
            # run_dateでフィルタ（指定時）
            if run_date:
                df = df[df.index.date <= run_date]
            return df
        except Exception as e:
            last_error = str(e)
            if attempt < retry_max:
                time.sleep(backoff_sec[min(attempt, len(backoff_sec) - 1)])

    return None


def ensure_cache_with_incremental_fetch(
    symbol: str,
    ticker: str,
    cache_path: Path,
    manifest: dict[str, dict],
    required_days: int,
    run_date: date | None = None,
    force: bool = False,
) -> dict:
    """
    キャッシュを確保（不足時のみ重い取得、通常は差分取得）。

    Args:
        symbol: シンボル（manifest用、例: "7203" または "1306.T"）
        ticker: yfinanceティッカー（例: "7203.T", "1306.T"）
        cache_path: キャッシュCSVパス
        manifest: manifest辞書（symbol -> エントリ）、この関数内で更新される
        required_days: 必要な営業日数
        run_date: 取得終了日（None時は今日）
        force: True時はmanifestを無視して全件再取得

    Returns:
        manifestエントリ（code/symbol, requested_days, fetched_bars, status, error, fetched_at）
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 変数の初期化
    cached_df = None
    need_full_fetch = False

    # manifestチェック（force時はスキップ）
    if not force:
        ent = manifest.get(symbol)
        if ent is not None:
            if ent.get("status") == "ok" and ent.get("fetched_bars", 0) >= required_days:
                # 差分取得チェック
                cached_df = load_cache(cache_path)
                if cached_df is not None and len(cached_df) > 0:
                    last_date = cached_df.index.max().date()
                    if run_date and last_date >= run_date:
                        # 既に最新まで取得済み
                        # 戻り値にnewly_fetched_daysを追加（既存のentを更新）
                        ent = ent.copy()
                        ent["newly_fetched_days"] = 0
                        return ent
                    # 差分取得を試みる
                    if run_date and last_date < run_date:
                        # 差分取得: 最後の日付+1日からrun_dateまでを取得
                        start_date = last_date + timedelta(days=1)
                        new_df = fetch_yf_data(
                            ticker, 
                            required_days, 
                            run_date, 
                            start_date=start_date,
                            retry_max=1, 
                            backoff_sec=[5]
                        )
                        if new_df is not None and len(new_df) > 0:
                            # 既存データより新しい日付のみを抽出
                            new_df_filtered = new_df[new_df.index.date > last_date]
                            if len(new_df_filtered) > 0:
                                # マージ
                                combined = pd.concat([cached_df, new_df_filtered])
                                combined = combined[~combined.index.duplicated(keep="last")]  # 同日は新しい方を優先
                                combined = combined.sort_index()
                                save_cache(cache_path, combined)
                                n_bars = len(combined)
                                newly_fetched_days = len(new_df_filtered)
                                status = "ok" if n_bars >= required_days else "insufficient"
                                ent = {
                                    "symbol": symbol,
                                    "requested_days": required_days,
                                    "fetched_bars": n_bars,
                                    "status": status,
                                    "error": None if n_bars >= required_days else "insufficient_bars",
                                    "fetched_at": now_iso,
                                    "newly_fetched_days": newly_fetched_days,
                                }
                                manifest[symbol] = ent
                                return ent
                        # 差分取得失敗 → フル取得に進む（次のパスに進まない）
                        need_full_fetch = True
                    else:
                        # 既に最新まで取得済みの場合は、次のパスに進まない
                        return ent
                else:
                    # キャッシュが空の場合は次のパスに進む
                    pass
            else:
                # manifestにエントリがない、または不足している場合は次のパスに進む
                pass

    # キャッシュ読み込み（最初のパスで既に読み込んでいる場合は再利用）
    if cached_df is None:
        cached_df = load_cache(cache_path)

    # 不足判定（最初のパスで差分取得を試みていない場合のみ）
    if not need_full_fetch:
        if cached_df is None:
            need_full_fetch = True
        else:
            n_bars = len(cached_df)
            if n_bars < required_days:
                need_full_fetch = True
            elif run_date:
                last_date = cached_df.index.max().date()
                if last_date < run_date:
                    # 差分取得を試みる（最初のパスで試みていない場合のみ）
                    start_date = last_date + timedelta(days=1)
                    new_df = fetch_yf_data(
                        ticker, 
                        required_days, 
                        run_date, 
                        start_date=start_date,
                        retry_max=1, 
                        backoff_sec=[5]
                    )
                    if new_df is not None and len(new_df) > 0:
                        # 既存データより新しい日付のみを抽出
                        new_df_filtered = new_df[new_df.index.date > last_date]
                        if len(new_df_filtered) > 0:
                            # マージ
                            combined = pd.concat([cached_df, new_df_filtered])
                            combined = combined[~combined.index.duplicated(keep="last")]
                            combined = combined.sort_index()
                            save_cache(cache_path, combined)
                            n_bars = len(combined)
                            newly_fetched_days = len(new_df_filtered)
                            status = "ok" if n_bars >= required_days else "insufficient"
                            ent = {
                                "symbol": symbol,
                                "requested_days": required_days,
                                "fetched_bars": n_bars,
                                "status": status,
                                "error": None if n_bars >= required_days else "insufficient_bars",
                                "fetched_at": now_iso,
                                "newly_fetched_days": newly_fetched_days,
                            }
                            manifest[symbol] = ent
                            return ent
                    # 差分取得失敗 → フル取得
                    need_full_fetch = True

    # フル取得
    if need_full_fetch or force:
        df = fetch_yf_data(ticker, required_days, run_date)
        if df is None or df.empty:
            ent = {
                "symbol": symbol,
                "requested_days": required_days,
                "fetched_bars": 0,
                "status": "failed",
                "error": "fetch_failed",
                "fetched_at": now_iso,
                "newly_fetched_days": 0,  # 取得失敗の場合は0
            }
            manifest[symbol] = ent
            return ent
        save_cache(cache_path, df)
        n_bars = len(df)
        status = "ok" if n_bars >= required_days else "insufficient"
        ent = {
            "symbol": symbol,
            "requested_days": required_days,
            "fetched_bars": n_bars,
            "status": status,
            "error": None if n_bars >= required_days else "insufficient_bars",
            "fetched_at": now_iso,
            "newly_fetched_days": n_bars,  # フル取得の場合は全データが新規
        }
        manifest[symbol] = ent
        return ent

    # 既存キャッシュが十分
    n_bars = len(cached_df)
    ent = {
        "symbol": symbol,
        "requested_days": required_days,
        "fetched_bars": n_bars,
        "status": "ok" if n_bars >= required_days else "insufficient",
        "error": None if n_bars >= required_days else "insufficient_bars",
        "fetched_at": now_iso,
        "newly_fetched_days": 0,  # 既存キャッシュが十分な場合は新規取得なし
    }
    manifest[symbol] = ent
    return ent
