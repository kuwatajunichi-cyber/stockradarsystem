"""
設定: 環境変数やキャッシュファイルパスを集中管理する。
"""
import os
from pathlib import Path

# 銘柄一覧ページ（固定。ここから最新ExcelのURLを抽出する）
DEFAULT_JPX_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"


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
    環境変数 LIQ_MIN_MEDIAN_TURNOVER_YEN 必須（未設定時は ValueError）。
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
    """RS算出の期間リスト（営業日数）。環境変数 RS_WINDOWS（default='63,126,252'）。"""
    raw = os.environ.get("RS_WINDOWS", "63,126,252").strip()
    if not raw:
        return [63, 126, 252]
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [63, 126, 252]


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


def get_yf_index_cache_dir(base_dir: Path) -> Path:
    """yfinance 指数キャッシュのルート。data/cache/yf_index/。"""
    return base_dir / "data" / "cache" / "yf_index"


def get_indicators_daily_dir(base_dir: Path) -> Path:
    """日次指標出力ディレクトリ。data/indicators/daily/。"""
    return base_dir / "data" / "indicators" / "daily"
