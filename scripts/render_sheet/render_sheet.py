"""
Google Drive 上の CSV を読み込み、Google スプレッドシートテンプレに流し込んで日次レポートを生成する。

- 入力: Drive 上の CSV（file ID または共有リンクで指定）
- 出力: テンプレを複製し、データ貼付・URL列表示名置換後のスプレッドシート
- 認証: OAuth（GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET / GDRIVE_OAUTH_REFRESH_TOKEN）
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
from pathlib import Path

import pandas as pd

# プロジェクトルートを PYTHONPATH に追加
_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.gdrive_smoketest.drive_client import (
    SHEETS_SCOPE,
    build_service,
    build_sheets_service,
    get_credentials,
    get_file_content,
    get_file_metadata,
)

logger = logging.getLogger(__name__)


# --- Drive リンク → fileId 抽出 ---
def extract_file_id(value: str) -> str:
    """
    Drive の file ID を抽出する。
    - 既に ID のみの場合はそのまま返す（英数字と一部記号、約33文字）
    - 共有リンクの場合は ID を抽出
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("ファイルIDまたは共有リンクが空です")
    # 共有リンク形式
    # https://drive.google.com/file/d/FILE_ID/view
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    # https://drive.google.com/open?id=FILE_ID
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    # フォルダリンクは file 用ではないが、ID 形式なら許容しない
    # 33文字前後の英数字-_ なら ID とみなす
    if re.match(r"^[a-zA-Z0-9_-]{20,50}$", s):
        return s
    raise ValueError(f"ファイルIDを抽出できませんでした: {value[:80]}...")


def extract_date_from_filename(name: str) -> str | None:
    """ファイル名から YYYY-MM-DD を抽出。例: indicators_20260221.csv -> 2026-02-21"""
    # YYYYMMDD
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        return m.group(0)
    return None


def col_index_to_a1(col: int) -> str:
    """0-based 列インデックスを A1 形式の列文字に変換。0->A, 25->Z, 26->AA"""
    result = []
    n = col
    while n >= 0:
        result.append(chr(ord("A") + (n % 26)))
        n = n // 26 - 1
    return "".join(reversed(result))


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
    template_spreadsheet_id: str | None,
    output_folder_id: str | None,
    header_anchor_sheet_name: str | None,
) -> dict:
    """コマンドライン・workflow inputs で上書きした最終設定を返す"""
    out = {
        "csv_drive_file_id": csv_drive_file_id or config.get("csv_drive_file_id"),
        "template_spreadsheet_id": template_spreadsheet_id or config.get("template_spreadsheet_id"),
        "output_folder_id": output_folder_id or config.get("output_folder_id"),
        "header_anchor_sheet_name": header_anchor_sheet_name or config.get("header_anchor_sheet_name", "indicators001"),
        "template_file_name": config.get("template_file_name", "indicators_template_v1.0"),
        "link_label_map": config.get("link_label_map") or {},
    }
    if not out["csv_drive_file_id"]:
        raise SystemExit("csv_drive_file_id が指定されていません。config または --csv-drive-file-id で指定してください。")
    if not out["output_folder_id"]:
        raise SystemExit("output_folder_id が指定されていません。config で指定してください。")
    if not out["header_anchor_sheet_name"]:
        raise SystemExit("header_anchor_sheet_name が指定されていません。")
    return out


# --- メイン処理 ---
def run(cfg: dict) -> str:
    """
    メイン処理。戻り値は生成したスプレッドシートの URL。
    """
    creds = get_credentials(extra_scopes=[SHEETS_SCOPE])
    drive = build_service(creds)
    sheets = build_sheets_service(creds)

    csv_file_id = extract_file_id(cfg["csv_drive_file_id"])

    # 1) CSV ダウンロード
    try:
        resp = get_file_content(drive, csv_file_id)
    except Exception as e:
        raise SystemExit(f"CSV のダウンロードに失敗しました。file_id={csv_file_id}: {e}") from e

    meta = get_file_metadata(drive, csv_file_id)
    csv_filename = meta.get("name", "")
    logger.info("入力CSV: %s (file_id=%s)", csv_filename, csv_file_id)

    df = pd.read_csv(io.BytesIO(resp))
    csv_rows = len(df)
    logger.info("入力CSV行数: %d", csv_rows)

    # 日付（出力ファイル名用）
    run_date = extract_date_from_filename(csv_filename)
    if not run_date:
        run_date = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m-%d")
        logger.warning("CSVファイル名から日付を抽出できず、本日を使用: %s", run_date)
    output_name = f"{run_date}_Daily"

    # 2) テンプレ取得
    template_id = cfg.get("template_spreadsheet_id")
    if not template_id:
        folder_id = cfg["output_folder_id"]
        template_name = cfg["template_file_name"]
        q = f"'{folder_id}' in parents and name = '{template_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        files = drive.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=2).execute()
        flist = files.get("files", [])
        if not flist:
            raise SystemExit(
                f"テンプレが見つかりません。folder_id={folder_id}, name={template_name}"
            )
        template_id = flist[0]["id"]
        logger.info("テンプレ取得: %s (id=%s)", template_name, template_id)

    # 3) テンプレ複製
    body = {"name": output_name, "parents": [cfg["output_folder_id"]]}
    copied = drive.files().copy(fileId=template_id, body=body, fields="id,name,webViewLink").execute()
    new_sheet_id = copied["id"]
    new_sheet_url = copied.get("webViewLink", f"https://docs.google.com/spreadsheets/d/{new_sheet_id}")
    logger.info("テンプレ複製完了: %s", new_sheet_url)

    # 4) スプレッドシート構造取得（namedRanges, sheets）
    ss = (
        sheets.spreadsheets()
        .get(
            spreadsheetId=new_sheet_id,
            fields="sheets,namedRanges",
        )
        .execute()
    )
    sheets_list = ss.get("sheets", [])
    named_ranges = ss.get("namedRanges", [])

    # シート名 → sheetId
    target_sheet_name = cfg["header_anchor_sheet_name"]
    target_sheet_id = None
    for sh in sheets_list:
        props = sh.get("properties", {})
        if props.get("title") == target_sheet_name:
            target_sheet_id = props.get("sheetId")
            break
    if target_sheet_id is None:
        raise SystemExit(
            f"シート '{target_sheet_name}' が見つかりません。"
            f"利用可能: {[s.get('properties', {}).get('title') for s in sheets_list]}"
        )

    # headerAnchor の NamedRange を探す（指定シートに紐づくもの）
    header_range = None
    for nr in named_ranges:
        if nr.get("name") != "headerAnchor":
            continue
        gr = nr.get("range", {})
        if gr.get("sheetId") == target_sheet_id:
            header_range = gr
            break
    if not header_range:
        raise SystemExit(
            f"headerAnchor がシート '{target_sheet_name}' に見つかりません。"
        )

    header_row = header_range.get("startRowIndex", 0)
    header_col_start = header_range.get("startColumnIndex", 0)

    # 5) テンプレヘッダー取得（headerAnchor から右方向、空セルまで）
    header_range_a1 = f"'{target_sheet_name}'!{col_index_to_a1(header_col_start)}{header_row + 1}"
    header_resp = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=new_sheet_id, range=header_range_a1, majorDimension="ROWS")
        .execute()
    )
    # 1行取得だが、横に広い範囲を取る必要がある。列数を多めに仮定して取得
    end_col = header_col_start + 100
    range_a1 = f"'{target_sheet_name}'!{col_index_to_a1(header_col_start)}{header_row + 1}:{col_index_to_a1(end_col)}{header_row + 1}"
    header_resp = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=new_sheet_id, range=range_a1, majorDimension="ROWS")
        .execute()
    )
    values = header_resp.get("values", [[]])
    template_headers = []
    if values:
        row0 = values[0]
        for i, v in enumerate(row0):
            cell = (v if isinstance(v, str) else str(v)).strip() if v is not None else ""
            if not cell:
                break
            template_headers.append(cell)

    logger.info("テンプレ列数: %d, ヘッダー: %s", len(template_headers), template_headers[:5])

    # 6) CSV → テンプレ列順に整形
    csv_columns = set(df.columns)
    template_set = set(template_headers)
    missing_in_csv = template_set - csv_columns
    extra_in_csv = csv_columns - template_set
    if missing_in_csv:
        logger.info("テンプレに存在するがCSVに無い列（空欄）: %s", sorted(missing_in_csv))
    if extra_in_csv:
        logger.info("CSVに存在するがテンプレに無い列（無視）: %s", sorted(extra_in_csv))

    def _to_sheet_value(val):
        if pd.isna(val):
            return ""
        if isinstance(val, (int, float)):
            return val
        return str(val)

    rows = []
    for _, r in df.iterrows():
        row = []
        for h in template_headers:
            if h in df.columns:
                row.append(_to_sheet_value(r[h]))
            else:
                row.append("")
        rows.append(row)

    data_start_row = header_row + 1  # 0-based → 1-based 行番号
    range_for_update = f"'{target_sheet_name}'!{col_index_to_a1(header_col_start)}{data_start_row + 1}:{col_index_to_a1(header_col_start + len(template_headers) - 1)}{data_start_row + len(rows)}"

    # 7) values.update でデータ貼付
    body = {"values": rows, "valueInputOption": "USER_ENTERED"}
    sheets.spreadsheets().values().update(
        spreadsheetId=new_sheet_id,
        range=range_for_update,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()

    last_row = data_start_row + len(rows)
    logger.info("書き込み最終行: %d (1-based)", last_row)

    # 書式設定済み範囲（仕様では約3000行強）
    format_threshold = 3000
    exceeded_format = last_row > format_threshold
    if exceeded_format:
        logger.warning("書式設定済み範囲（約%d行）を超えて書き込みました。超過分は書式が適用されない可能性があります。", format_threshold)
    else:
        logger.info("書式設定済み範囲内で書き込みました。")

    # 8) URL 列の表示名置換
    link_label_map = cfg.get("link_label_map") or {}
    url_replace_by_col = {}
    use_hyperlink_fallback = False

    for col_idx, col_name in enumerate(template_headers):
        if col_name not in link_label_map:
            continue
        label = link_label_map[col_name]
        col_letter = col_index_to_a1(header_col_start + col_idx)
        col_replace_count = 0

        # 優先: textFormatRuns で rich text / フォールバック: =HYPERLINK(url, label)
        all_cell_data = []
        for idx in range(len(df)):
            url_val = df.iloc[idx].get(col_name)
            if pd.isna(url_val) or not str(url_val).strip().startswith("http"):
                all_cell_data.append({"userEnteredValue": {"stringValue": ""}})
            else:
                url_str = str(url_val).strip()
                all_cell_data.append({
                    "userEnteredValue": {"stringValue": label},
                    "textFormatRuns": [{"startIndex": 0, "format": {"link": {"uri": url_str}}}],
                })
                col_replace_count += 1

        try:
            req = {
                "updateCells": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": data_start_row,
                        "endRowIndex": data_start_row + len(df),
                        "startColumnIndex": header_col_start + col_idx,
                        "endColumnIndex": header_col_start + col_idx + 1,
                    },
                    "rows": [{"values": [cd]} for cd in all_cell_data],
                    "fields": "userEnteredValue,textFormatRuns",
                }
            }
            sheets.spreadsheets().batchUpdate(spreadsheetId=new_sheet_id, body={"requests": [req]}).execute()
            url_replace_by_col[col_name] = col_replace_count
        except Exception as e:
            logger.warning("textFormatRuns による URL 置換に失敗。HYPERLINK 式でフォールバック: %s", e)
            use_hyperlink_fallback = True
            hyperlink_rows = []
            for idx in range(len(df)):
                url_val = df.iloc[idx].get(col_name)
                if pd.isna(url_val) or not str(url_val).strip().startswith("http"):
                    hyperlink_rows.append([""])
                else:
                    url_str = str(url_val).strip().replace('"', '""')
                    hyperlink_rows.append([f'=HYPERLINK("{url_str}","{label}")'])
                    col_replace_count += 1
            range_hy = f"'{target_sheet_name}'!{col_letter}{data_start_row + 1}:{col_letter}{data_start_row + len(df)}"
            sheets.spreadsheets().values().update(
                spreadsheetId=new_sheet_id,
                range=range_hy,
                valueInputOption="USER_ENTERED",
                body={"values": hyperlink_rows},
            ).execute()
            url_replace_by_col[col_name] = col_replace_count

    if use_hyperlink_fallback:
        logger.info("URL列は HYPERLINK 式（フォールバック）で設定しました。")

    total_url_replace = sum(url_replace_by_col.values())
    logger.info("URL置換件数: 合計=%d, 列別=%s", total_url_replace, url_replace_by_col)

    # 9) 出力 URL をログ
    logger.info("出力スプレッドシートURL: %s", new_sheet_url)

    return new_sheet_url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive CSV を読み込み、Sheets テンプレに流し込んで日次レポートを生成"
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
        "--template-spreadsheet-id",
        default=None,
        help="テンプレのスプレッドシート ID（省略時は config の template_file_name で検索）",
    )
    parser.add_argument(
        "--output-folder-id",
        default=None,
        help="出力先フォルダ ID（省略時は config を使用）",
    )
    parser.add_argument(
        "--header-anchor-sheet-name",
        default=None,
        help="headerAnchor が存在するシート名（省略時は config を使用）",
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
        template_spreadsheet_id=args.template_spreadsheet_id,
        output_folder_id=args.output_folder_id,
        header_anchor_sheet_name=args.header_anchor_sheet_name,
    )

    url = run(cfg)
    # Actions で参照しやすいよう最後に URL を出力
    print(f"spreadsheet_url={url}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        logger.exception("エラー: %s", e)
        sys.exit(1)
