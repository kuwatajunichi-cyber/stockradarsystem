"""
Google Drive 上の CSV を読み込み、ローカル XLSX テンプレートに流し込んで日次レポートを生成する。

- 入力: Drive 上の CSV（file ID または共有リンクで指定）
- テンプレ: ローカル XLSX（openpyxl で処理）
- 出力: XLSX を Drive にアップロード
- 認証: OAuth（GDRIVE_OAUTH_*、Drive API のみ・Sheets API 不要）
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
from pathlib import Path

import pandas as pd

# openpyxl はパス変更前にインポート（sys.path の影響を受けないように）
from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

# プロジェクトルートを PYTHONPATH に追加
_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.gdrive.drive_client import (
    DriveAdapter,
    GoogleDriveAdapter,
    build_service,
    get_credentials,
    get_file_metadata,
    get_or_create_folder,
    upload_file,
)

logger = logging.getLogger(__name__)

# XLSX MIME type
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- Drive リンク → fileId 抽出 ---
def extract_file_id(value: str) -> str:
    """Drive の file ID を抽出する。"""
    s = (value or "").strip()
    if not s:
        raise ValueError("ファイルIDまたは共有リンクが空です")
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{20,50}$", s):
        return s
    raise ValueError(f"ファイルIDを抽出できませんでした: {value[:80]}...")


def extract_date_from_filename(name: str) -> str | None:
    """ファイル名から YYYY-MM-DD を抽出。"""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        return m.group(0)
    return None


# --- 設定読み込み ---
def load_config(config_path: Path) -> dict:
    """config YAML を読み込む"""
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML がインストールされていません。pip install pyyaml を実行してください。")

    if not config_path.exists():
        raise SystemExit(f"設定ファイルが見つかりません: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_config(
    config: dict,
    csv_drive_file_id: str | None,
    output_folder_id: str | None,
    output_subfolder: str | None,
    header_anchor_sheet_name: str | None,
    template_path: str | Path | None,
) -> dict:
    """コマンドライン・workflow inputs で上書きした最終設定を返す"""
    out = {
        "csv_drive_file_id": csv_drive_file_id or config.get("csv_drive_file_id"),
        "output_folder_id": output_folder_id or config.get("output_folder_id"),
        "output_subfolder": output_subfolder or config.get("output_subfolder"),
        "header_anchor_sheet_name": header_anchor_sheet_name or config.get("header_anchor_sheet_name", "indicators001"),
        "template_path": template_path or config.get("template_path"),
        "link_label_map": config.get("link_label_map") or {},
        "sort_column": config.get("sort_column"),
        "sort_ascending": config.get("sort_ascending", False),
    }
    if not out["csv_drive_file_id"]:
        raise SystemExit("csv_drive_file_id が指定されていません。")
    if not out["output_folder_id"]:
        raise SystemExit("output_folder_id が指定されていません。")
    if not out["header_anchor_sheet_name"]:
        raise SystemExit("header_anchor_sheet_name が指定されていません。")
    if not out["template_path"]:
        raise SystemExit("template_path が指定されていません。config/render_sheet.yaml で設定してください。")
    return out


def _parse_header_anchor(wb, sheet_name: str) -> tuple[int, int]:
    """
    headerAnchor の Named Range から (1-based row, 1-based col) を返す。
    sheet_name と一致するシートの headerAnchor のみ採用。
    """
    dn = wb.defined_names.get("headerAnchor")
    if not dn:
        raise SystemExit("Named Range 'headerAnchor' がテンプレートに見つかりません。")

    for title, coord in dn.destinations:
        if title != sheet_name:
            continue
        # coord は "A5" や "A5:E5" の形式。先頭セルを取得
        addr = coord.replace("$", "").split(":")[0]
        col_letter, row = coordinate_from_string(addr)
        col_idx = column_index_from_string(col_letter)
        return (row, col_idx)
    raise SystemExit(
        f"headerAnchor がシート '{sheet_name}' に見つかりません。"
        f"利用可能: {[s for s in wb.sheetnames]}"
    )


def _read_template_headers(ws, header_row: int, header_col: int, max_cols: int = 100) -> list[str]:
    """ヘッダー行を左から読み、空セルで終了するまで取得。"""
    headers = []
    for c in range(header_col, header_col + max_cols):
        cell = ws.cell(row=header_row, column=c)
        val = cell.value
        if val is None or (isinstance(val, str) and not val.strip()):
            break
        headers.append(str(val).strip())
    return headers


# --- メイン処理 ---
def run(cfg: dict, drive_adapter: DriveAdapter | None = None) -> str:
    """
    メイン処理。戻り値は生成したファイルの Drive URL。
    drive_adapter 未指定時は get_credentials + build_service で本番接続する。
    テスト時は FakeDriveAdapter を渡して Secrets 不要で実行可能。
    """
    if drive_adapter is None:
        creds = get_credentials()
        service = build_service(creds)
        drive: DriveAdapter = GoogleDriveAdapter(service)
    else:
        drive = drive_adapter

    csv_file_id = extract_file_id(cfg["csv_drive_file_id"])

    # 1) CSV ダウンロード
    try:
        resp = drive.get_file_content(csv_file_id)
    except Exception as e:
        raise SystemExit(f"CSV のダウンロードに失敗しました。file_id={csv_file_id}: {e}") from e

    meta = drive.get_file_metadata(csv_file_id)
    csv_filename = meta.get("name", "")
    logger.info("入力CSV: %s (file_id=%s)", csv_filename, csv_file_id)

    df = pd.read_csv(io.BytesIO(resp))
    csv_rows = len(df)
    logger.info("入力CSV行数: %d", csv_rows)

    # ソート（設定あり且つ列が存在する場合）
    sort_column = cfg.get("sort_column")
    if sort_column and sort_column in df.columns:
        sort_asc = cfg.get("sort_ascending", False)
        df = df.sort_values(by=sort_column, ascending=sort_asc, na_position="last")
        logger.info("ソート適用: %s %s", sort_column, "昇順" if sort_asc else "降順")
    elif sort_column:
        logger.warning("ソートキー列 '%s' がCSVに存在しないため、ソートをスキップしました。", sort_column)

    # 日付（出力ファイル名用）
    run_date = extract_date_from_filename(csv_filename)
    if not run_date:
        run_date = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m-%d")
        logger.warning("CSVファイル名から日付を抽出できず、本日を使用: %s", run_date)
    output_name = f"{run_date}_Daily.xlsx"

    # 2) テンプレート読み込み（ローカル）
    template_path = Path(cfg["template_path"])
    if not template_path.is_absolute():
        template_path = _repo_root / template_path
    if not template_path.exists():
        raise SystemExit(f"テンプレートが見つかりません: {template_path}")

    logger.info("テンプレート: %s", template_path)
    wb = load_workbook(template_path, data_only=False)
    target_sheet_name = cfg["header_anchor_sheet_name"]
    if target_sheet_name not in wb.sheetnames:
        raise SystemExit(f"シート '{target_sheet_name}' が見つかりません。利用可能: {wb.sheetnames}")

    ws = wb[target_sheet_name]

    # 3) headerAnchor からヘッダー位置・ヘッダー一覧取得
    header_row, header_col = _parse_header_anchor(wb, target_sheet_name)
    template_headers = _read_template_headers(ws, header_row, header_col)
    logger.info("テンプレ列数: %d, ヘッダー: %s", len(template_headers), template_headers[:5])

    # 4) CSV → テンプレ列順に整形
    csv_columns = set(df.columns)
    template_set = set(template_headers)
    missing_in_csv = template_set - csv_columns
    extra_in_csv = csv_columns - template_set
    if missing_in_csv:
        logger.info("テンプレに存在するがCSVに無い列（空欄）: %s", sorted(missing_in_csv))
    if extra_in_csv:
        logger.info("CSVに存在するがテンプレに無い列（無視）: %s", sorted(extra_in_csv))

    def _to_value(val):
        if pd.isna(val):
            return ""
        if isinstance(val, (int, float)):
            return val
        return str(val)

    data_start_row = header_row + 1
    link_label_map = cfg.get("link_label_map") or {}
    hyperlink_font = Font(u="single", color="0563C1")

    for row_idx, (_, r) in enumerate(df.iterrows()):
        excel_row = data_start_row + row_idx
        for col_idx, h in enumerate(template_headers):
            cell = ws.cell(row=excel_row, column=header_col + col_idx)
            if h in df.columns:
                val = r[h]
                if h in link_label_map:
                    # URL列: 表示名＋ハイパーリンク
                    label = link_label_map[h]
                    if pd.notna(val) and str(val).strip().startswith("http"):
                        url_str = str(val).strip()
                        cell.value = label
                        cell.hyperlink = url_str
                        cell.font = hyperlink_font
                    else:
                        cell.value = _to_value(val)
                else:
                    cell.value = _to_value(val)
            else:
                cell.value = ""

    last_row = data_start_row + len(df) - 1
    logger.info("書き込み最終行: %d (1-based)", last_row)

    format_threshold = 3000
    if last_row > format_threshold:
        logger.warning("書式設定済み範囲（約%d行）を超えて書き込みました。", format_threshold)
    else:
        logger.info("書式設定済み範囲内で書き込みました。")

    url_cols = [c for c in template_headers if c in link_label_map]
    url_count = sum(1 for _, r in df.iterrows() for c in url_cols if c in r and pd.notna(r.get(c)) and str(r.get(c)).startswith("http"))
    logger.info("URL置換件数: %d (列: %s)", url_count, url_cols)

    # 5) 一時ファイルに保存
    output_dir = _repo_root / "data" / "indicators" / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name
    wb.save(output_path)
    logger.info("ローカル保存: %s", output_path)

    # 6) Drive にアップロード
    content = output_path.read_bytes()
    parent_id = cfg["output_folder_id"]
    if cfg.get("output_subfolder"):
        parent_id = drive.get_or_create_folder(parent_id, cfg["output_subfolder"])
        logger.info("出力先サブフォルダ: %s", cfg["output_subfolder"])
    file_id, web_link = drive.upload_file(
        parent_id, output_name, content, mime_type=MIME_XLSX
    )
    result_url = web_link or f"https://drive.google.com/file/d/{file_id}/view"
    logger.info("出力URL: %s", result_url)

    return result_url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive CSV を読み込み、XLSX テンプレに流し込んで日次レポートを生成"
    )
    parser.add_argument(
        "--csv-drive-file-id",
        required=True,
        help="CSV の Drive ファイル ID または共有リンク",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_repo_root / "config" / "render_sheet.yaml",
        help="設定 YAML パス",
    )
    parser.add_argument(
        "--output-folder-id",
        default=None,
        help="出力先フォルダ ID（省略時は config を使用）",
    )
    parser.add_argument(
        "--output-subfolder",
        default=None,
        help="出力先サブフォルダ名（例: YYYY-MM）。未設定時は output_folder_id 直下に保存",
    )
    parser.add_argument(
        "--header-anchor-sheet-name",
        default=None,
        help="headerAnchor が存在するシート名（省略時は config を使用）",
    )
    parser.add_argument(
        "--template-path",
        default=None,
        help="テンプレート XLSX のパス（省略時は config を使用）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログ",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    config = load_config(args.config)
    cfg = resolve_config(
        config,
        csv_drive_file_id=args.csv_drive_file_id,
        output_folder_id=args.output_folder_id,
        output_subfolder=args.output_subfolder,
        header_anchor_sheet_name=args.header_anchor_sheet_name,
        template_path=args.template_path,
    )

    url = run(cfg)
    print(f"spreadsheet_url={url}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        logger.exception("エラー: %s", e)
        sys.exit(1)
