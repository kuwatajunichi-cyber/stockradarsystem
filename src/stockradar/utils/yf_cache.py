"""
yfinance取得ラッパとキャッシュI/Oの共通コンポーネント。

- 分割取得、sleep、retry、merge、barsカウント
- cache I/O（銘柄別csv、manifest jsonl）
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from stockradar.config import (
    get_yf_retry_backoff_sec,
    get_yf_retry_max,
    get_yf_sleep_sec_between_batches,
)

MANIFEST_FILENAME = "_manifest.jsonl"
# ユニバース一括取得用（日次 Job が触らない）
MANIFEST_UNIVERSE_FILENAME = "_manifest_universe.jsonl"
_REQUIRED_OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

ERROR_INSUFFICIENT_BARS = "insufficient_bars"
ERROR_MISSING_BAR_FOR_RUN_DATE = "missing_bar_for_run_date"


def classify_cache_row_status(
    n_bars: int,
    required_days: int,
    last_date: date | None,
    run_date: date | None,
) -> tuple[str, str | None]:
    """
    キャッシュ1本の行数と最終日から status / error を決める。

    - insufficient: 歴史本数不足のみ（fetched_bars < required_days）
    - stale: run_date あり・本数十分だが max(index).date() < run_date
    - ok: 上記以外で十分かつ run_date なし、または last_date >= run_date
    """
    if n_bars < required_days:
        return "insufficient", ERROR_INSUFFICIENT_BARS
    if run_date is None:
        return "ok", None
    if last_date is None:
        return "stale", ERROR_MISSING_BAR_FOR_RUN_DATE
    if last_date < run_date:
        return "stale", ERROR_MISSING_BAR_FOR_RUN_DATE
    return "ok", None


def build_manifest_entry(
    symbol: str,
    *,
    requested_days: int,
    fetched_bars: int,
    status: str,
    error: str | None,
    fetched_at: str,
    newly_fetched_days: int,
) -> dict:
    """日次 manifest 用: code と symbol を同一値で保持（JSONL 1行契約）。"""
    return {
        "code": symbol,
        "symbol": symbol,
        "requested_days": requested_days,
        "fetched_bars": fetched_bars,
        "status": status,
        "error": error,
        "fetched_at": fetched_at,
        "newly_fetched_days": newly_fetched_days,
    }


def rebuild_manifest_entry_from_disk(
    symbol: str,
    cache_path: Path,
    *,
    requested_days: int,
    run_date: date | None,
    fetched_at: str,
) -> dict:
    """
    ディスク上のキャッシュ CSV を唯一の真実として manifest 1 行を組み立て直す。

    ensure のメモリ内更新・分岐取りこぼし・manifest 手編集と実ファイルの差を、
    update_manifest の直前に解消する。
    """
    df = load_cache(cache_path)
    if df is None or df.empty:
        return build_manifest_entry(
            symbol,
            requested_days=requested_days,
            fetched_bars=0,
            status="insufficient",
            error=ERROR_INSUFFICIENT_BARS,
            fetched_at=fetched_at,
            newly_fetched_days=0,
        )
    missing_cols = _missing_required_ohlcv_columns(df)
    n_bars = len(df)
    last_date = df.index.max().date()
    if missing_cols:
        return build_manifest_entry(
            symbol,
            requested_days=requested_days,
            fetched_bars=n_bars,
            status="insufficient",
            error=f"schema_mismatch_missing_ohlcv:{','.join(missing_cols)}",
            fetched_at=fetched_at,
            newly_fetched_days=0,
        )
    st, err = classify_cache_row_status(n_bars, requested_days, last_date, run_date)
    return build_manifest_entry(
        symbol,
        requested_days=requested_days,
        fetched_bars=n_bars,
        status=st,
        error=None if st == "ok" else err,
        fetched_at=fetched_at,
        newly_fetched_days=0,
    )


def _missing_required_ohlcv_columns(df: pd.DataFrame | None) -> list[str]:
    """キャッシュDataFrameに不足している必須OHLCV列を返す。"""
    if df is None:
        return list(_REQUIRED_OHLCV_COLUMNS)
    return [col for col in _REQUIRED_OHLCV_COLUMNS if col not in df.columns]


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
    schema_mismatch_reason: str | None = None
    # ディスク上の旧スキーマ起因でフル取得した場合、修復後も error に残してログ集計できるようにする
    schema_repair_reason: str | None = None

    # manifestチェック（force時はスキップ）
    # status==ok でも CSV 実体の last_date / 本数を必ず照合（manifest のみの誤 ok を防ぐ）
    if not force:
        ent = manifest.get(symbol)
        if ent is not None:
            if ent.get("status") == "ok" and ent.get("fetched_bars", 0) >= required_days:
                cached_df = load_cache(cache_path)
                if cached_df is not None and len(cached_df) > 0:
                    missing_cols = _missing_required_ohlcv_columns(cached_df)
                    has_schema_mismatch = bool(missing_cols)
                    if has_schema_mismatch:
                        schema_mismatch_reason = f"schema_mismatch_missing_ohlcv:{','.join(missing_cols)}"
                    last_date = cached_df.index.max().date()
                    n_disk = len(cached_df)
                    st, err = classify_cache_row_status(
                        n_disk, required_days, last_date, run_date
                    )
                    if st == "ok" and not has_schema_mismatch:
                        out = build_manifest_entry(
                            symbol,
                            requested_days=required_days,
                            fetched_bars=n_disk,
                            status="ok",
                            error=None,
                            fetched_at=now_iso,
                            newly_fetched_days=0,
                        )
                        manifest[symbol] = out
                        return out
                    if has_schema_mismatch:
                        schema_repair_reason = schema_mismatch_reason
                        need_full_fetch = True
                    elif st == "insufficient":
                        need_full_fetch = True
                    elif st == "stale" and run_date:
                        start_date = last_date + timedelta(days=1)
                        new_df = fetch_yf_data(
                            ticker,
                            required_days,
                            run_date,
                            start_date=start_date,
                            retry_max=1,
                            backoff_sec=[5],
                        )
                        if new_df is not None and len(new_df) > 0:
                            new_df_filtered = new_df[new_df.index.date > last_date]
                            if len(new_df_filtered) > 0:
                                combined = pd.concat([cached_df, new_df_filtered])
                                combined = combined[
                                    ~combined.index.duplicated(keep="last")
                                ]
                                combined = combined.sort_index()
                                save_cache(cache_path, combined)
                                n_bars = len(combined)
                                newly_fetched_days = len(new_df_filtered)
                                ld = combined.index.max().date()
                                st2, err2 = classify_cache_row_status(
                                    n_bars, required_days, ld, run_date
                                )
                                out = build_manifest_entry(
                                    symbol,
                                    requested_days=required_days,
                                    fetched_bars=n_bars,
                                    status=st2,
                                    error=err2,
                                    fetched_at=now_iso,
                                    newly_fetched_days=newly_fetched_days,
                                )
                                manifest[symbol] = out
                                return out
                        need_full_fetch = True
                # キャッシュが空 → 次パスへ
            # manifest にエントリがない、または manifest 上不足 → 次パスへ
            pass

    # キャッシュ読み込み（最初のパスで既に読み込んでいる場合は再利用）
    if cached_df is None:
        cached_df = load_cache(cache_path)

    # 不足判定（最初のパスで差分取得を試みていない場合のみ）
    if not need_full_fetch:
        if cached_df is None:
            need_full_fetch = True
        else:
            missing_cols = _missing_required_ohlcv_columns(cached_df)
            if missing_cols:
                schema_mismatch_reason = f"schema_mismatch_missing_ohlcv:{','.join(missing_cols)}"
                schema_repair_reason = schema_mismatch_reason
                need_full_fetch = True
            n_bars = len(cached_df)
            if not need_full_fetch and n_bars < required_days:
                need_full_fetch = True
            elif not need_full_fetch and run_date:
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
                            ld = combined.index.max().date()
                            st_m, err_m = classify_cache_row_status(
                                n_bars, required_days, ld, run_date
                            )
                            out = build_manifest_entry(
                                symbol,
                                requested_days=required_days,
                                fetched_bars=n_bars,
                                status=st_m,
                                error=err_m,
                                fetched_at=now_iso,
                                newly_fetched_days=newly_fetched_days,
                            )
                            manifest[symbol] = out
                            return out
                    # 差分取得失敗 → フル取得
                    need_full_fetch = True

    # フル取得
    if need_full_fetch or force:
        df = fetch_yf_data(ticker, required_days, run_date)
        if df is None or df.empty:
            ent = build_manifest_entry(
                symbol,
                requested_days=required_days,
                fetched_bars=0,
                status="failed",
                error="fetch_failed",
                fetched_at=now_iso,
                newly_fetched_days=0,
            )
            manifest[symbol] = ent
            return ent
        save_cache(cache_path, df)
        n_bars = len(df)
        last_date = df.index.max().date()
        miss_after = _missing_required_ohlcv_columns(df)
        schema_after: str | None = (
            f"schema_mismatch_missing_ohlcv:{','.join(miss_after)}"
            if miss_after
            else None
        )
        st, err = classify_cache_row_status(
            n_bars, required_days, last_date, run_date
        )
        if st == "ok" and schema_after is not None:
            final_err: str | None = schema_after
        elif st == "ok" and schema_repair_reason is not None:
            final_err = schema_repair_reason
        elif st == "ok":
            final_err = None
        else:
            final_err = err
        ent = build_manifest_entry(
            symbol,
            requested_days=required_days,
            fetched_bars=n_bars,
            status=st,
            error=final_err,
            fetched_at=now_iso,
            newly_fetched_days=n_bars,
        )
        manifest[symbol] = ent
        return ent

    # 既存キャッシュが十分（マージ・フル取得が不要な場合）
    assert cached_df is not None
    n_bars = len(cached_df)
    last_date = cached_df.index.max().date()
    st, err = classify_cache_row_status(
        n_bars, required_days, last_date, run_date
    )
    ent = build_manifest_entry(
        symbol,
        requested_days=required_days,
        fetched_bars=n_bars,
        status=st,
        error=None if st == "ok" else err,
        fetched_at=now_iso,
        newly_fetched_days=0,
    )
    manifest[symbol] = ent
    return ent
