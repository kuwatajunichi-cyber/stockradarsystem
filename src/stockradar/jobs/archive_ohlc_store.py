"""
OHLCストアアーカイブジョブ（出口処理）。

prune（730日より古いデータ削除）→ zip化して保存する。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from stockradar.config import get_yf_daily_cache_dir
from stockradar.utils.yf_cache import MANIFEST_FILENAME

RETENTION_DAYS = 730  # 保持期間（日）


def prune_ohlc_store(store_dir: Path, retention_days: int = RETENTION_DAYS) -> None:
    """
    OHLCストアをpruneする（retention_daysより古いデータを削除）。

    Args:
        store_dir: OHLCストアディレクトリ（data/cache/yf_daily/）
        retention_days: 保持期間（日）
    """
    cutoff_date = date.today() - timedelta(days=retention_days)
    print(f"prune開始: cutoff_date={cutoff_date.isoformat()}, retention_days={retention_days}", file=sys.stderr)

    pruned_count = 0
    deleted_count = 0

    # 各銘柄CSVをprune
    for csv_path in store_dir.glob("*.csv"):
        if csv_path.name == MANIFEST_FILENAME:
            continue  # manifestは後で処理

        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", index_col=0)
            if df.empty:
                continue

            df.index = pd.to_datetime(df.index)
            original_len = len(df)

            # cutoff_dateより古い行を削除
            df_pruned = df[df.index.date >= cutoff_date]

            if len(df_pruned) < original_len:
                pruned_count += 1
                if len(df_pruned) == 0:
                    # 空になったら削除
                    csv_path.unlink()
                    deleted_count += 1
                    print(f"削除: {csv_path.name} (全データが古すぎる)", file=sys.stderr)
                else:
                    # 残ったデータを保存
                    df_pruned.to_csv(csv_path, encoding="utf-8-sig")
                    print(f"prune: {csv_path.name} ({original_len} -> {len(df_pruned)}行)", file=sys.stderr)
        except Exception as e:
            print(f"警告: {csv_path.name} のpruneに失敗: {type(e).__name__}: {e}", file=sys.stderr)
            continue

    # manifest JSONLをprune
    manifest_path = store_dir / MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            entries = []
            with open(manifest_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ent = json.loads(line)
                        # fetched_atでフィルタ（イベント日付として使用）
                        fetched_at_str = ent.get("fetched_at", "")
                        if fetched_at_str:
                            try:
                                fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
                                fetched_date = fetched_at.date()
                                if fetched_date >= cutoff_date:
                                    entries.append(ent)
                            except (ValueError, AttributeError):
                                # 日付解析失敗時は保持（安全側）
                                entries.append(ent)
                        else:
                            # fetched_atがない場合は保持（安全側）
                            entries.append(ent)
                    except json.JSONDecodeError:
                        continue

            # manifestを書き戻し
            with open(manifest_path, "w", encoding="utf-8") as f:
                for ent in entries:
                    f.write(json.dumps(ent, ensure_ascii=False) + "\n")

            print(f"manifest prune: {len(entries)}エントリ保持", file=sys.stderr)
        except Exception as e:
            print(f"警告: manifestのpruneに失敗: {type(e).__name__}: {e}", file=sys.stderr)

    print(f"prune完了: pruned={pruned_count}, deleted={deleted_count}", file=sys.stderr)


def archive_ohlc_store(base_dir: Path | None = None, retention_days: int = RETENTION_DAYS) -> None:
    """
    OHLCストアをpruneしてzip化する。

    Args:
        base_dir: プロジェクトルート（None時はカレントディレクトリ）
        retention_days: 保持期間（日）
    """
    base = base_dir or Path.cwd()
    store_dir = get_yf_daily_cache_dir(base)
    archive_dir = base / "data" / "cache" / "ohlc_store_archive"
    archive_zip = archive_dir / "ohlc_store.zip"

    if not store_dir.exists():
        print(f"警告: ストアディレクトリが存在しません: {store_dir}（空zipを作成）", file=sys.stderr)
        archive_dir.mkdir(parents=True, exist_ok=True)
        # 空zipを作成
        with zipfile.ZipFile(archive_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            pass
        print(f"空zip作成完了: {archive_zip}", file=sys.stderr)
        return

    # prune実行
    prune_ohlc_store(store_dir, retention_days)

    # zip化
    print(f"zip化開始: {store_dir} -> {archive_zip}", file=sys.stderr)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 既存のzipを削除（上書きのため）
    if archive_zip.exists():
        archive_zip.unlink()

    try:
        with zipfile.ZipFile(archive_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            # ストアディレクトリ内の全ファイルをzipに追加
            for file_path in store_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(store_dir)
                    zf.write(file_path, arcname)

        zip_size = archive_zip.stat().st_size
        print(f"zip化完了: {archive_zip} ({zip_size:,} bytes)", file=sys.stderr)
    except Exception as e:
        print(f"エラー: zip作成に失敗しました: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Archive OHLC store (prune + zip).")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=RETENTION_DAYS,
        help=f"保持期間（日、default={RETENTION_DAYS}）",
    )
    args = parser.parse_args(argv)

    try:
        archive_ohlc_store(retention_days=args.retention_days)
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
