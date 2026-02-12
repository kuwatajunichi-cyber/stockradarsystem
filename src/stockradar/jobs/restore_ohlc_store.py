"""
OHLCストア復元ジョブ（入口処理）。

data/cache/ohlc_store_archive/ohlc_store.zip から data/cache/yf_daily/ を復元する。
zipが存在しない場合は空構造を初期化する。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from stockradar.config import get_yf_daily_cache_dir


def restore_ohlc_store(base_dir: Path | None = None) -> None:
    """
    OHLCストアを復元する。

    Args:
        base_dir: プロジェクトルート（None時はカレントディレクトリ）
    """
    base = base_dir or Path.cwd()
    archive_dir = base / "data" / "cache" / "ohlc_store_archive"
    archive_zip = archive_dir / "ohlc_store.zip"
    store_dir = get_yf_daily_cache_dir(base)

    # zipが存在する場合
    if archive_zip.exists():
        print(f"復元: {archive_zip} -> {store_dir}", file=sys.stderr)
        # 既存のストアディレクトリを削除（残骸混入防止）
        if store_dir.exists():
            shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)

        # zipを展開
        try:
            with zipfile.ZipFile(archive_zip, "r") as zf:
                zf.extractall(store_dir)
            print(f"復元完了: {store_dir}", file=sys.stderr)
        except Exception as e:
            print(f"エラー: zip展開に失敗しました: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # zipが存在しない場合：空構造を初期化
        print(f"zipが見つかりません: {archive_zip}（空構造を初期化）", file=sys.stderr)
        if store_dir.exists():
            shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)
        # manifestファイルを空で作成（必要に応じて）
        manifest_path = store_dir / "_manifest.jsonl"
        if not manifest_path.exists():
            manifest_path.touch()
        print(f"初期化完了: {store_dir}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Restore OHLC store from zip archive.")
    args = parser.parse_args(argv)

    try:
        restore_ohlc_store()
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
