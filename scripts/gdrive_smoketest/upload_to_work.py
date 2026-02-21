"""
0011_work にファイルをアップロードする CLI。
月次: 0011_work/YYYY-MM/ 直下に配置（月フォルダが無ければ作成）。
日次: 0011_work/YYYY-MM/YYYY-MM-DD/ 直下に配置（月・日フォルダが無ければ作成）。
OAuth 環境変数 GDRIVE_OAUTH_* を参照する。認証情報はログに出さない。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(_script_dir))
sys.path.insert(0, _repo_root)
from scripts.gdrive_smoketest.drive_client import (
    FOLDER_ID_WORK,
    build_service,
    get_credentials,
    get_or_create_folder,
    upload_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload files to 0011_work (month folder and optionally day folder)."
    )
    parser.add_argument(
        "--month",
        required=True,
        metavar="YYYY-MM",
        help="月フォルダ名（例: 2026-02）",
    )
    parser.add_argument(
        "--day",
        metavar="YYYY-MM-DD",
        help="日フォルダ名（指定時は 0011_work/月/日/ に配置）",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="アップロードするファイルパス",
    )
    args = parser.parse_args()

    month = args.month.strip()
    day = args.day.strip() if args.day else None
    if not month or len(month) != 7 or month[4] != "-":
        print("エラー: --month は YYYY-MM 形式で指定してください。", file=sys.stderr)
        sys.exit(1)
    if day and (len(day) != 10 or day[4] != "-" or day[7] != "-"):
        print("エラー: --day は YYYY-MM-DD 形式で指定してください。", file=sys.stderr)
        sys.exit(1)

    creds = get_credentials()
    service = build_service(creds)

    month_id = get_or_create_folder(service, FOLDER_ID_WORK, month)
    if day:
        parent_id = get_or_create_folder(service, month_id, day)
        target_path = f"0011_work/{month}/{day}/"
    else:
        parent_id = month_id
        target_path = f"0011_work/{month}/"

    last_file_id = None
    for path_str in args.files:
        path = Path(path_str)
        if not path.is_file():
            print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
            sys.exit(1)
        content = path.read_bytes()
        name = path.name
        file_id, web_link = upload_file(
            service, parent_id, name, content, mime_type="text/csv"
        )
        last_file_id = file_id
        print(f"[Drive] {name} -> {target_path} (id={file_id})", file=sys.stderr)
    print(f"Uploaded {len(args.files)} file(s) to {target_path}", file=sys.stderr)
    if last_file_id:
        print(f"csv_file_id={last_file_id}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
