"""
JPX銘柄一覧Excelをダウンロードし、rawに保存・processedにCSV(utf-8-sig)出力するジョブ。

- URLは環境変数 JPX_LIST_URL から取得（コード直書き禁止）。
- 取得ファイルは .xls（旧形式）または .xlsx を想定。内容で形式を判定し拡張子を付けて保存する。
- 出力: data/raw/jpx/jpx_list_YYYYMMDD.xls または .xlsx, data/processed/jpx/jpx_list_YYYYMMDD.csv
- 列選択・renameは未実装（TODO）。
"""
from pathlib import Path
from datetime import date

import pandas as pd
import requests

from stockradar.config import get_jpx_list_url
from stockradar.io.http import download_bytes

# 形式判定用: xlsx は ZIP 先頭 PK、xls は OLE2 のマジックバイト（1a e0 / 1a e1 等の変種あり）
_MAGIC_XLSX = b"PK"
_MAGIC_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1"  # OLE2 Compound Document（先頭6バイト）


def _detect_excel_format(content: bytes) -> str:
    """先頭バイトから .xls / .xlsx を判定。未対応の場合は例外。"""
    if content.startswith(_MAGIC_XLSX):
        return "xlsx"
    if content.startswith(_MAGIC_XLS):
        return "xls"
    hint = "JPX_LIST_URL に Excel ファイル（.xls または .xlsx）の直リンクを指定してください。"
    if content.lstrip().startswith((b"<", b"<!", b"<?xml")):
        raise RuntimeError(
            f"ダウンロード結果がExcel形式ではありません（HTML/XMLの可能性）。{hint}"
        )
    raise RuntimeError(
        f"ダウンロード結果がExcel形式ではありません（先頭バイト: {content[:8]!r}）。{hint}"
    )


def run(
    base_dir: Path | None = None,
    run_date: date | None = None,
) -> tuple[Path, Path]:
    """
    銘柄一覧を取得し、形式に応じて raw に .xls/.xlsx 保存し、CSV を出力する。
    base_dir 未指定時はカレントディレクトリを基準にする。
    戻り値: (raw_excel_path, csv_path)
    """
    base = base_dir or Path.cwd()
    d = run_date or date.today()
    suffix = d.strftime("%Y%m%d")

    raw_dir = base / "data" / "raw" / "jpx"
    processed_dir = base / "data" / "processed" / "jpx"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    csv_path = processed_dir / f"jpx_list_{suffix}.csv"

    # 1) URL取得（未設定時はここで例外）
    url = get_jpx_list_url()

    # 2) ダウンロード（HTTPエラー時は raise_for_status で例外）
    try:
        content = download_bytes(url)
    except requests.RequestException as e:
        raise RuntimeError(f"JPX銘柄一覧のダウンロードに失敗しました: {url}") from e

    # 2.5) 形式判定し、拡張子を付けて保存（.xls / .xlsx のまま保存する）
    fmt = _detect_excel_format(content)
    raw_path = raw_dir / f"jpx_list_{suffix}.{fmt}"
    try:
        raw_path.write_bytes(content)
    except OSError as e:
        raise RuntimeError(f"Excelファイルの保存に失敗しました: {raw_path}") from e

    # 4) Excel → CSV（列選択・renameはTODO）
    _cause = lambda e: f" — 原因: {type(e).__name__}: {e}"
    try:
        if fmt == "xlsx":
            df = pd.read_excel(raw_path, engine="openpyxl")
        else:
            df = pd.read_excel(raw_path, engine="xlrd")
    except Exception as e:
        raise RuntimeError(
            f"Excelの読み込みに失敗しました: {raw_path}{_cause(e)}"
        ) from e
    try:
        # TODO: 列選択・rename（実ファイル仕様に合わせて追加）
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except Exception as e:
        raise RuntimeError(
            f"CSVの書き込みに失敗しました: {csv_path}{_cause(e)}"
        ) from e

    return raw_path, csv_path


def main() -> None:
    """CLIエントリ: 例外時はメッセージを表示して終了コード1で終了。"""
    try:
        raw_path, csv_path = run()
        print(f"保存: {raw_path}")
        print(f"出力: {csv_path}")
    except (ValueError, RuntimeError) as e:
        print(f"エラー: {e}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
