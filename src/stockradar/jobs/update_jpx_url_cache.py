"""
URL更新ジョブ（独立）: ページから最新の銘柄一覧Excel URL を解決し、
成功時のみ data/cache/jpx_latest_url.txt を更新する。

失敗時はキャッシュがあればそのまま（WARN ログ）、無ければエラー。
ダウンロードは行わない。
"""
import logging
import sys
from pathlib import Path

from stockradar.sources.jpx_resolver import resolve_and_update_cache

# 標準出力にも WARN が出るようにする
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)


def main() -> None:
    base = Path.cwd()
    try:
        url = resolve_and_update_cache(base)
        print(url)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
