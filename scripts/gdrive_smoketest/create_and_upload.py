"""
ワークフローA用: 0011_work に 今月/今日フォルダを作成し、run_id 入りテストファイルをアップロードする。
JST 基準の YYYY-MM / YYYY-MM-DD。出力は GITHUB_OUTPUT 用に stdout に出す（Secrets は出さない）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import pytz

# リポジトリルートを path に追加（Actions では repo root が cwd）
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


def jst_now() -> datetime:
    return datetime.now(pytz.timezone("Asia/Tokyo"))


def main() -> None:
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    creds = get_credentials()
    service = build_service(creds)

    now = jst_now()
    month_folder = now.strftime("%Y-%m")
    day_folder = now.strftime("%Y-%m-%d")

    # 0011_work 直下に 今月 → 今日
    month_id = get_or_create_folder(service, FOLDER_ID_WORK, month_folder)
    day_id = get_or_create_folder(service, month_id, day_folder)

    file_name = f"smoke_{run_id}.txt"
    content = json.dumps(
        {
            "run_id": run_id,
            "created_at_jst": now.isoformat(),
            "month_folder": month_folder,
            "day_folder": day_folder,
        },
        ensure_ascii=False,
        indent=2,
    )

    file_id, web_view_link = upload_file(
        service, day_id, file_name, content, mime_type="text/plain"
    )

    # ログ用（Secrets は含めない）
    print(f"[A-1] 月フォルダ: {month_folder}, 日フォルダ: {day_folder}", file=sys.stderr)
    print(f"[A-1] アップロード: {file_name}, fileId: {file_id}", file=sys.stderr)
    if web_view_link:
        print(f"[A-1] webViewLink: {web_view_link}", file=sys.stderr)

    # GITHUB_OUTPUT 用（multiline は <<EOF で渡す想定のため key=value のみ）
    out = {
        "run_id": run_id,
        "month_folder": month_folder,
        "day_folder": day_folder,
        "file_name": file_name,
        "file_id": file_id,
        "web_view_link": web_view_link or "",
    }
    for k, v in out.items():
        print(f"{k}={v}")


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
