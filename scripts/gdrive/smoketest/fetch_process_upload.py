"""
ワークフローB用: 0011_work から A が作ったファイルを取得し、加工して 0012_paid に配置する。
A から渡された run_id / month_folder / day_folder / file_id で一意特定。
加工: 元内容に processed_at, run_id, sha256 を追記（テキスト/JSON 両対応）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytz

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.gdrive.drive_client import (
    build_service,
    get_folder_id_paid,
    get_credentials,
    get_file_content,
    get_file_metadata,
    get_or_create_folder,
    upload_file,
)


def process_content(raw: bytes, run_id: str) -> tuple[str, str]:
    """
    元内容に processed_at, run_id, sha256 を付与する。
    戻り値: (加工後テキスト, sha256hex)
    """
    sha = hashlib.sha256(raw).hexdigest()
    now = datetime.now(pytz.timezone("Asia/Tokyo")).isoformat()
    suffix = f"\n\n# processed_at={now}\n# run_id={run_id}\n# sha256={sha}\n"

    try:
        text = raw.decode("utf-8")
        # JSON ならキー追加して整形
        try:
            data = json.loads(text)
            data["processed_at"] = now
            data["run_id"] = run_id
            data["sha256"] = sha
            return json.dumps(data, ensure_ascii=False, indent=2), sha
        except json.JSONDecodeError:
            pass
        return text.rstrip() + suffix, sha
    except UnicodeDecodeError:
        return "(binary)" + suffix, sha


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch from work, process, upload to paid.")
    parser.add_argument("--run-id", required=True, help="GITHUB_RUN_ID")
    parser.add_argument("--month-folder", required=True, help="YYYY-MM")
    parser.add_argument("--day-folder", required=True, help="YYYY-MM-DD")
    parser.add_argument("--file-id", required=True, help="0011_work 上のファイル ID")
    parser.add_argument("--file-name", default="", help="元ファイル名（ログ用）")
    args = parser.parse_args()

    creds = get_credentials()
    service = build_service(creds)

    # B-1: 取得
    try:
        raw = get_file_content(service, args.file_id)
    except Exception as e:
        print(
            f"エラー: ファイル取得に失敗しました（権限不足・対象未共有・ファイル未発見の可能性）。file_id={args.file_id}: {e}",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    meta = get_file_metadata(service, args.file_id)
    src_name = meta.get("name") or args.file_name or args.file_id
    print(f"[B-1] 取得元(work): file_name={src_name}, file_id={args.file_id}", file=sys.stderr)

    # B-2 / B-3: 加工 → 出力先作成 → アップロード
    processed_text, sha256_val = process_content(raw, args.run_id)
    out_name = f"smoke_{args.run_id}_processed.txt"

    month_id = get_or_create_folder(service, get_folder_id_paid(), args.month_folder)
    day_id = get_or_create_folder(service, month_id, args.day_folder)

    file_id, web_view_link = upload_file(
        service, day_id, out_name, processed_text, mime_type="text/plain"
    )

    print(
        f"[B-4] 出力先(paid): 月={args.month_folder}, 日={args.day_folder}",
        file=sys.stderr,
    )
    print(f"[B-4] 加工後ファイル: {out_name}, fileId: {file_id}", file=sys.stderr)
    if web_view_link:
        print(f"[B-4] webViewLink: {web_view_link}", file=sys.stderr)
    print(f"[B-4] 加工内容: 末尾に processed_at, run_id, sha256 を追記", file=sys.stderr)

    out = {
        "src_file_name": src_name,
        "src_file_id": args.file_id,
        "paid_month_folder": args.month_folder,
        "paid_day_folder": args.day_folder,
        "out_file_name": out_name,
        "out_file_id": file_id,
        "out_web_view_link": web_view_link or "",
        "sha256": sha256_val,
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
