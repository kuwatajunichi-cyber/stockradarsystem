"""
yfinance 用設定のスニペット（スタンドアロン）。

他プロジェクトにコピーしてそのまま使える。stockradar に依存しない。
環境変数: YF_BATCH_SIZE, YF_SLEEP_SEC_BETWEEN_BATCHES, YF_RETRY_MAX, YF_RETRY_BACKOFF_SEC
"""
import os
from pathlib import Path


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


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
