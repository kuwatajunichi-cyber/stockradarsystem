"""
0012_paid 配下で 3 か月より古い月フォルダ（YYYY-MM）を削除する CLI。
Drive 凍結解除後に有効化する想定。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.gdrive.drive_client import (
    build_service,
    get_credentials,
    get_folder_id_paid,
)

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _cutoff_ym(today: date) -> str:
    """今日から 3 か月前より古い月の境界。YYYY-MM < この値の月を削除する。"""
    year, month = today.year, today.month
    month -= 3
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Drive 0012_paid の 3 か月より古い月フォルダを削除する。"
    )
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

    creds = get_credentials()
    service = build_service(creds)
    parent_id = get_folder_id_paid()

    q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    page_token = None
    deleted = 0
    while True:
        resp = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id, name)",
                pageSize=100,
                pageToken=page_token or "",
            )
            .execute()
        )
        for f in resp.get("files") or []:
            name = f.get("name", "")
            if MONTH_PATTERN.match(name) and name < cutoff:
                try:
                    service.files().delete(fileId=f["id"]).execute()
                    deleted += 1
                    print(f"削除: {name} ({f['id']})", file=sys.stderr)
                except Exception as e:
                    print(f"削除失敗 {name}: {e}", file=sys.stderr)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"Drive 0012_paid クリーンアップ完了（削除数: {deleted}）", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

