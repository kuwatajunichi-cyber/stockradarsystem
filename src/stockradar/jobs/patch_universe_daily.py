"""
日次ユニバースパッチジョブ。

月次ベースの core CSV に対し、JPX 上場廃止銘柄を除外して出力する。
出力ディレクトリに manifest.json（base_release, base_release_date, run_date, delisted_removed_count）を書き、
指標ワークフローで「いずれか新しい方」判定に使う。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from stockradar.jobs.resolve_trading_day import resolve_trading_day
from stockradar.utils.cli_parse import parse_run_date_opt
from stockradar.sources.jpx_delisted import (
    apply_delisted_patch,
    fetch_delisted_codes,
)

MANIFEST_FILENAME = "manifest.json"


def _parse_base_release_date(base_release: str) -> str | None:
    """monthly-YYYYMMDD から YYYY-MM-DD を返す。形式が合わなければ None。"""
    m = re.match(r"monthly-(\d{4})(\d{2})(\d{2})", (base_release or "").strip())
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Apply delisted patch to universe core CSV and write manifest.",
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="入力 core CSV パス（例: equity_domestic_core_with_name.csv）",
    )
    parser.add_argument(
        "--run-date",
        type=str,
        help="基準日 YYYY-MM-DD（省略時は Asia/Tokyo の今日）",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="出力 CSV パス（省略時は data/universe/jpx/patched_cache/equity_domestic_core_with_name.csv）",
    )
    parser.add_argument(
        "--base-release",
        type=str,
        help="使用した月次Releaseタグ（例: monthly-20260207）。manifest に記録し指標側の比較に利用。",
    )
    args = parser.parse_args(argv)

    run_date = parse_run_date_opt(args.run_date)
    base = Path.cwd()
    if run_date is None:
        run_date, _ = resolve_trading_day(None)

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = base / input_path
    if not input_path.exists():
        print(f"エラー: 入力ファイルが存在しません: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = base / "data" / "universe" / "jpx" / "patched_cache" / "equity_domestic_core_with_name.csv"
    if not output_path.is_absolute():
        output_path = base / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_csv(input_path)
    except Exception as e:
        print(f"エラー: 入力CSVの読み込みに失敗しました: {input_path} — {e}", file=sys.stderr)
        sys.exit(1)

    if "code" not in df.columns:
        print("エラー: 入力CSVに code 列がありません。", file=sys.stderr)
        sys.exit(1)

    delisted_codes = fetch_delisted_codes(run_date, lookback_months=2)
    before_count = len(df)
    df_patched = apply_delisted_patch(df, delisted_codes)
    after_count = len(df_patched)
    removed = before_count - after_count

    try:
        df_patched.to_csv(output_path, index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"エラー: 出力CSVの書き込みに失敗しました: {output_path} — {e}", file=sys.stderr)
        sys.exit(1)

    base_release_date = _parse_base_release_date(args.base_release) if args.base_release else None
    manifest = {
        "base_release": args.base_release or None,
        "base_release_date": base_release_date,
        "run_date": run_date.isoformat(),
        "delisted_removed_count": removed,
    }
    manifest_path = output_path.parent / MANIFEST_FILENAME
    try:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"警告: manifest の書き込みに失敗しました: {manifest_path} — {e}", file=sys.stderr)

    print(f"output={output_path}")
    print(f"removed={removed}")


if __name__ == "__main__":
    main()
