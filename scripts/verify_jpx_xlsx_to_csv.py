"""
検証用: 既存の jpx_list_*.xls / jpx_list_*.xlsx を読み、CSV 出力までを実行し、
失敗した場合は原因（例外タイプ・メッセージ・トレースバック）を表示する。

使い方（プロジェクトルートで）:
  python scripts/verify_jpx_xlsx_to_csv.py
  python scripts/verify_jpx_xlsx_to_csv.py "data/raw/jpx/jpx_list_20260207.xls"
"""
import sys
from pathlib import Path

import pandas as pd


def _excel_engine(path: Path) -> str:
    """内容の先頭バイトで .xls(OLE2) / .xlsx(ZIP) を判定。リネームされたファイルにも対応。"""
    head = path.read_bytes()[:8]
    if head.startswith(b"PK"):
        return "openpyxl"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1"):  # OLE2（1a e0 / 1a e1 等の変種あり）
        return "xlrd"
    raise RuntimeError(
        f"Excel形式ではありません（先頭バイト: {head!r}）。.xls または .xlsx を指定してください。"
    )


def main() -> None:
    base = Path.cwd()
    if len(sys.argv) >= 2:
        excel_path = Path(sys.argv[1])
        if not excel_path.is_absolute():
            excel_path = base / excel_path
    else:
        # 直近の jpx_list_*.xls / jpx_list_*.xlsx を探す（xls を優先）
        raw_dir = base / "data" / "raw" / "jpx"
        if not raw_dir.exists():
            print(f"エラー: ディレクトリがありません: {raw_dir}", file=sys.stderr)
            sys.exit(1)
        xls = sorted(raw_dir.glob("jpx_list_*.xls"), reverse=True)
        xlsx = sorted(raw_dir.glob("jpx_list_*.xlsx"), reverse=True)
        candidates = xls + xlsx
        if not candidates:
            print(
                f"エラー: jpx_list_*.xls / jpx_list_*.xlsx がありません: {raw_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        excel_path = candidates[0]

    stem = excel_path.stem  # jpx_list_YYYYMMDD
    csv_path = base / "data" / "processed" / "jpx" / f"{stem}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    engine = _excel_engine(excel_path)
    print(f"読み込み: {excel_path} (engine={engine})")
    print(f"出力先:  {csv_path}")

    try:
        df = pd.read_excel(excel_path, engine=engine)
        print(f"  → 行数={len(df)}, 列数={len(df.columns)}")
    except Exception:
        print("Excelの読み込みで例外が発生しました:", file=sys.stderr)
        raise

    try:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print("CSVの書き込みに成功しました.")
    except Exception:
        print("CSVの書き込みで例外が発生しました:", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
