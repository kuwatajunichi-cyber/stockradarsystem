"""
設定: 環境変数やキャッシュファイルパスを集中管理する。
"""
import os
from pathlib import Path

# 銘柄一覧ページ（固定。ここから最新ExcelのURLを抽出する）
DEFAULT_JPX_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"


def get_http_timeout() -> int:
    """HTTP リクエストのタイムアウト秒。環境変数 HTTP_TIMEOUT（default=60）。"""
    return _env_int("HTTP_TIMEOUT", 60)


def get_jpx_page_timeout() -> int:
    """JPX ページ取得のタイムアウト秒。環境変数 JPX_PAGE_TIMEOUT（default=30）。"""
    return _env_int("JPX_PAGE_TIMEOUT", 30)


def get_git_command_timeout() -> int:
    """git コマンド実行のタイムアウト秒。環境変数 GIT_COMMAND_TIMEOUT（default=5）。"""
    return _env_int("GIT_COMMAND_TIMEOUT", 5)


def get_jpx_page_url() -> str:
    """最新URLを抽出する対象ページ。環境変数 JPX_PAGE_URL がなければ既定値。"""
    url = os.environ.get("JPX_PAGE_URL", "").strip()
    return url or DEFAULT_JPX_PAGE_URL


def get_jpx_list_url_override() -> str | None:
    """手動で固定する場合は JPX_LIST_URL_OVERRIDE を設定。指定時は絶対優先。"""
    url = os.environ.get("JPX_LIST_URL_OVERRIDE", "").strip()
    return url or None


def get_jpx_cache_path(base_dir: Path) -> Path:
    """銘柄一覧Excel URLのキャッシュファイルパス。"""
    return base_dir / "data" / "cache" / "jpx_latest_url.txt"


def get_jpx_market_product_categories_cache_path(base_dir: Path) -> Path:
    """「市場・商品区分」のカテゴリ集合キャッシュファイルパス。"""
    return base_dir / "data" / "cache" / "jpx_market_product_categories.json"


# 上場廃止銘柄一覧ページ（日次パッチ用）
DEFAULT_JPX_DELISTED_PAGE_URL = "https://www.jpx.co.jp/listing/stocks/delisted/index.html"


def get_jpx_delisted_page_url() -> str:
    """上場廃止銘柄一覧ページURL。環境変数 JPX_DELISTED_PAGE_URL がなければ既定値。"""
    url = os.environ.get("JPX_DELISTED_PAGE_URL", "").strip()
    return url or DEFAULT_JPX_DELISTED_PAGE_URL


def get_jpx_delisted_page_timeout() -> int:
    """上場廃止ページ取得のタイムアウト秒。環境変数 JPX_DELISTED_PAGE_TIMEOUT（default=30）。"""
    return _env_int("JPX_DELISTED_PAGE_TIMEOUT", 30)


def get_jpx_limit_table_path(base_dir: Path | None = None) -> Path:
    """JPX制限値幅テーブルの設定ファイルパス。環境変数 JPX_LIMIT_TABLE_PATH で上書き可能。"""
    path = os.environ.get("JPX_LIMIT_TABLE_PATH", "").strip()
    if path:
        return Path(path)
    base = base_dir or Path.cwd()
    return base / "config" / "jpx_limit_table.yaml"


# --- 二次ユニバース（equity_domestic 分割）・yfinance 取得用 ---

def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(key: str, default: float | None) -> float | None:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def get_ipo_lookback_days() -> int:
    """IPO判定に必要な営業日数。環境変数 IPO_LOOKBACK_DAYS（default=252）。"""
    return _env_int("IPO_LOOKBACK_DAYS", 252)


def get_liq_lookback_days() -> int:
    """流動性判定の直近営業日数。環境変数 LIQ_LOOKBACK_DAYS（default=60）。"""
    return _env_int("LIQ_LOOKBACK_DAYS", 60)


def get_liq_min_median_turnover_yen() -> float:
    """
    流動性閾値（円）。中央値がこれ未満なら illiquid。
    環境変数 LIQ_MIN_MEDIAN_TURNOVER_YEN（未設定時は 20,000,000 を使用。負の値の場合は ValueError）。
    """
    v = _env_float("LIQ_MIN_MEDIAN_TURNOVER_YEN", 20000000)
    if v is None or v < 0:
        raise ValueError(
            "環境変数 LIQ_MIN_MEDIAN_TURNOVER_YEN を設定してください（例: 10000000）。"
        )
    return v


def get_yf_batch_size() -> int:
    """yfinance 取得のバッチサイズ。環境変数 YF_BATCH_SIZE（default=100）。"""
    return _env_int("YF_BATCH_SIZE", 100)


def get_yf_sleep_sec_between_batches() -> int:
    """バッチ間スリープ秒。環境変数 YF_SLEEP_SEC_BETWEEN_BATCHES（default=5）。"""
    return _env_int("YF_SLEEP_SEC_BETWEEN_BATCHES", 5)


def get_yf_retry_max() -> int:
    """バッチ内銘柄の最大再試行回数。環境変数 YF_RETRY_MAX（default=3）。"""
    return _env_int("YF_RETRY_MAX", 3)


def get_yf_retry_backoff_sec() -> list[int]:
    """再試行時の待機秒数リスト。環境変数 YF_RETRY_BACKOFF_SEC（default='5,15,30'）。"""
    raw = os.environ.get("YF_RETRY_BACKOFF_SEC", "5,15,30").strip()
    if not raw:
        return [5, 15, 30]
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [5, 15, 30]


def get_yf_daily_cache_dir(base_dir: Path) -> Path:
    """yfinance 日次キャッシュのルート。data/cache/yf_daily/。"""
    return base_dir / "data" / "cache" / "yf_daily"


# --- 日次指標算出用 ---

def get_z_lookback_days() -> int:
    """出来高zscoreの窓サイズ（営業日数）。環境変数 Z_LOOKBACK_DAYS（default=60）。"""
    return _env_int("Z_LOOKBACK_DAYS", 60)


def get_rs_windows() -> list[int]:
    """RS算出の期間リスト（営業日数）。環境変数 RS_WINDOWS（default='31,63,126,252'）。"""
    raw = os.environ.get("RS_WINDOWS", "31,63,126,252").strip()
    if not raw:
        return [31, 63, 126, 252]
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [31, 63, 126, 252]


def get_rs_benchmark() -> str:
    """RS算出のベンチマーク。環境変数 RS_BENCHMARK（default='BOTH'）。TOPIX/NIKKEI/BOTH。"""
    v = os.environ.get("RS_BENCHMARK", "BOTH").strip().upper()
    if v in ("TOPIX", "NIKKEI", "BOTH"):
        return v
    return "BOTH"


def get_rs_weights() -> list[float] | None:
    """RS合成用の重みリスト。環境変数 RS_WEIGHTS（default=None）。"""
    raw = os.environ.get("RS_WEIGHTS", "").strip()
    if not raw:
        return None
    try:
        weights = [float(x.strip()) for x in raw.split(",") if x.strip()]
        if len(weights) > 0:
            return weights
        return None
    except ValueError:
        return None


def get_buffer_days() -> int:
    """キャッシュ取得時のバッファ日数。環境変数 BUFFER_DAYS（default=20）。"""
    return _env_int("BUFFER_DAYS", 20)


def get_stale_retry_max_passes() -> int:
    """
    run_date 指定時、manifest が stale の銘柄に対する再試行を含めた最大パス数。
    環境変数 STALE_RETRY_MAX_PASSES（default=3: 初回 + 待機後最大2回）。
    """
    return _env_int("STALE_RETRY_MAX_PASSES", 3)


def get_stale_retry_sleep_sec() -> int:
    """stale 再試行前の待機秒。環境変数 STALE_RETRY_SLEEP_SEC（default=300=5分）。"""
    return _env_int("STALE_RETRY_SLEEP_SEC", 300)


def get_stale_allow_continue_max_count() -> int:
    """
    stale 残存時に処理継続を許容する上限件数。
    環境変数 STALE_ALLOW_CONTINUE_MAX_COUNT（default=9）。
    """
    return _env_int("STALE_ALLOW_CONTINUE_MAX_COUNT", 9)


def get_yf_index_cache_dir(base_dir: Path) -> Path:
    """yfinance 指数キャッシュのルート。data/cache/yf_index/。"""
    return base_dir / "data" / "cache" / "yf_index"


def get_index_store_archive_dir(base_dir: Path) -> Path:
    """指数ストア zip の保存ディレクトリ。data/cache/index_store_archive/。"""
    return base_dir / "data" / "cache" / "index_store_archive"


def get_index_store_archive_zip_path(base_dir: Path) -> Path:
    """指数ストア zip ファイルパス（index_store.zip）。"""
    return get_index_store_archive_dir(base_dir) / "index_store.zip"


def get_indicators_daily_dir(base_dir: Path) -> Path:
    """日次指標出力ディレクトリ。data/indicators/daily/。"""
    return base_dir / "data" / "indicators" / "daily"


def get_indicators_max_workers() -> int | None:
    """
    指標算出の並列ワーカー上限。環境変数 INDICATORS_MAX_WORKERS（未設定時は自動）。
    1未満や不正値は None（自動）扱い。
    """
    v = os.environ.get("INDICATORS_MAX_WORKERS", "").strip()
    if not v:
        return None
    try:
        n = int(v)
    except ValueError:
        return None
    return n if n >= 1 else None


def get_universe_jpx_dir(base_dir: Path) -> Path:
    """ユニバースJPXディレクトリ。data/universe/jpx/。"""
    return base_dir / "data" / "universe" / "jpx"


def get_processed_jpx_dir(base_dir: Path) -> Path:
    """JPX処理済みディレクトリ。data/processed/jpx/。"""
    return base_dir / "data" / "processed" / "jpx"
