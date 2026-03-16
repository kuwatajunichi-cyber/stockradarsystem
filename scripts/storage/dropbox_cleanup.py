"""
Dropbox 上で 3 か月より古い月の成果物を削除する CLI。
--today の属する月を M0、M-1, M-2 を残し、M-3 以下を削除する。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.storage.dropbox_client import DropboxStorageAdapter


def _cutoff_ym(today: date) -> str:
    """今日から 3 か月前より古い月の境界。YYYY-MM < この値の月を削除する。"""
    year, month = today.year, today.month
    month -= 3
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Dropbox の 3 か月より古い成果物を削除する。")
    parser.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        default=None,
        help="基準日（省略時は今日）",
    )
    args = parser.parse_args()

    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print(f"エラー: --today は YYYY-MM-DD 形式で指定してください: {args.today}", file=sys.stderr)
            sys.exit(1)
    else:
        today = date.today()

    cutoff = _cutoff_ym(today)
    print(f"削除対象: YYYY-MM < {cutoff}", file=sys.stderr)

    adapter = DropboxStorageAdapter()
    try:
        adapter.delete_older_than(cutoff)
        print("Dropbox クリーンアップ完了", file=sys.stderr)
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
