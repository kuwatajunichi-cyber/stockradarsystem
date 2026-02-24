"""
JPX銘柄一覧Excelをダウンロードし、rawに保存・processedにCSV(utf-8-sig)出力するジョブ。

- URL決定: JPX_LIST_URL_OVERRIDE があればそれを採用、なければ resolve_and_update_cache（ページから最新URL解決→失敗時はキャッシュ）。
- 取得ファイルは .xls / .xlsx を想定。内容で形式を判定し拡張子を付けて保存する。
- 出力: data/raw/jpx/jpx_list_YYYYMMDD.xls または .xlsx, data/processed/jpx/jpx_list_YYYYMMDD.csv
- 列選択・renameは未実装（TODO）。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from stockradar.config import get_jpx_list_url_override
from stockradar.io.http import download_bytes
from stockradar.sources.jpx_resolver import resolve_and_update_cache

# 形式判定用: xlsx は ZIP 先頭 PK、xls は OLE2 のマジックバイト（1a e0 / 1a e1 等の変種あり）
_MAGIC_XLSX = b"PK"
_MAGIC_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1"  # OLE2 Compound Document（先頭6バイト）


def detect_excel_format(content: bytes) -> str:
    """
    先頭バイトから .xls / .xlsx を判定する（Pure）。
    未対応の場合は RuntimeError。
    """
    if content.startswith(_MAGIC_XLSX):
        return "xlsx"
    if content.startswith(_MAGIC_XLS):
        return "xls"
    hint = "Excel の直リンクを指定するか、JPX_LIST_URL_OVERRIDE で固定URLを設定してください。"
    if content.lstrip().startswith((b"<", b"<!", b"<?xml")):
        raise RuntimeError(
            f"ダウンロード結果がExcel形式ではありません（HTML/XMLの可能性）。{hint}"
        )
    raise RuntimeError(
        f"ダウンロード結果がExcel形式ではありません（先頭バイト: {content[:8]!r}）。{hint}"
    )


def excel_content_to_csv_bytes(content: bytes, fmt: str) -> bytes:
    """
    Excel のバイ列を CSV（utf-8-sig）のバイ列に変換する（Pure）。
    I/O は行わず、メモリ上で read_excel → to_csv する。
    """
    from io import BytesIO

    bio = BytesIO(content)
    if fmt == "xlsx":
        df = pd.read_excel(bio, engine="openpyxl")
    else:
        df = pd.read_excel(bio, engine="xlrd")
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def run(
    base_dir: Path | None = None,
    run_date: date | None = None,
    *,
    downloader: Callable[[str], bytes] | None = None,
) -> tuple[Path, Path]:
    """
    銘柄一覧を取得し、形式に応じて raw に .xls/.xlsx 保存し、CSV を出力する。
    base_dir 未指定時はカレントディレクトリを基準にする。
    downloader 未指定時は download_bytes を使用する。

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

    # 1) URL決定（OVERRIDE 優先、なければページ解決→キャッシュフォールバック）
    override = get_jpx_list_url_override()
    if override is not None:
        url = override
    else:
        url = resolve_and_update_cache(base)

    # 2) ダウンロード
    get_bytes = downloader if downloader is not None else download_bytes
    try:
        content = get_bytes(url)
    except requests.RequestException as e:
        raise RuntimeError(f"JPX銘柄一覧のダウンロードに失敗しました: {url}") from e
    except Exception as e:
        raise RuntimeError(f"JPX銘柄一覧のダウンロードに失敗しました: {url}") from e

    # 3) 形式判定し、拡張子を付けて保存
    fmt = detect_excel_format(content)
    raw_path = raw_dir / f"jpx_list_{suffix}.{fmt}"
    try:
        raw_path.write_bytes(content)
    except OSError as e:
        raise RuntimeError(f"Excelファイルの保存に失敗しました: {raw_path}") from e

    # 4) Excel → CSV（Pure 関数で変換してから書き込み）
    _cause = lambda e: f" — 原因: {type(e).__name__}: {e}"
    try:
        csv_bytes = excel_content_to_csv_bytes(content, fmt)
    except Exception as e:
        raise RuntimeError(
            f"Excelの読み込みに失敗しました: {raw_path}{_cause(e)}"
        ) from e
    try:
        csv_path.write_bytes(csv_bytes)
    except OSError as e:
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
