"""
JPX processed CSV から一次ユニバース（universe_primary）を構築するジョブ。

入力:
    - data/processed/jpx/jpx_list_YYYYMMDD.csv など（--input で指定可）

出力:
    - data/universe/jpx/universe_master_YYYYMMDD.csv
      columns: date, code, name, market_product_raw, universe_primary
    - data/universe/jpx/sets_YYYYMMDD/{universe_id}.csv
      1列: code（ヘッダ付き）, universe_id は 7種

ユニバース設計に関するスキーマ変化は ALERT[UNIVERSE_SCHEMA] として標準エラーに出力するが、
ジョブは継続し、unknown へのフォールバックを行う。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from stockradar.universe.jpx_primary import UNIVERSE_IDS, build_universe_from_jpx
from stockradar.utils.paths import find_latest_processed_jpx


def _infer_date_from_filename(path: Path) -> date | None:
    m = re.search(r"(\d{8})", path.name)
    if not m:
        return None
    ymd = m.group(1)
    try:
        return date(int(ymd[0:4]), int(ymd[4:6]), int(ymd[6:8]))
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build primary universe from JPX processed CSV."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="入力CSVパス（省略時は data/processed/jpx/jpx_list_*.csv の最新を自動選択）",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = base / input_path
    else:
        input_path = find_latest_processed_jpx(base)
        if input_path is None:
            print(
                "エラー: 入力CSVが見つかりません。--input で明示するか、"
                "data/processed/jpx/jpx_list_YYYYMMDD.csv を作成してください。",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if not input_path.exists():
        print(f"エラー: 入力CSVが存在しません: {input_path}", file=sys.stderr)
        raise SystemExit(1)

    as_of = _infer_date_from_filename(input_path) or date.today()

    try:
        df = pd.read_csv(input_path)
    except Exception as e:  # pragma: no cover - I/O 保護
        print(f"エラー: 入力CSVの読み込みに失敗しました: {input_path} — {e}", file=sys.stderr)
        raise SystemExit(1)

    try:
        universe_df, messages = build_universe_from_jpx(df, as_of, base)
    except ValueError as e:
        # スキーマ破壊レベルのエラー（必須列欠損 / コード重複など）はジョブ失敗扱い
        print(f"エラー: {e}", file=sys.stderr)
        raise SystemExit(1)

    # ALERT / WARN は標準エラーに出すが、ジョブは継続
    for msg in messages.all_messages():
        print(msg, file=sys.stderr)

    # 出力先パス
    ymd = as_of.strftime("%Y%m%d")
    universe_dir = base / "data" / "universe" / "jpx"
    universe_dir.mkdir(parents=True, exist_ok=True)

    master_path = universe_dir / f"universe_master_{ymd}.csv"
    sets_dir = universe_dir / f"sets_{ymd}"
    sets_dir.mkdir(parents=True, exist_ok=True)

    try:
        universe_df.to_csv(master_path, index=False, encoding="utf-8-sig")
    except Exception as e:  # pragma: no cover - I/O 保護
        print(f"エラー: universe_master の書き込みに失敗しました: {master_path} — {e}", file=sys.stderr)
        raise SystemExit(1)

    # 各 universe_id ごとの銘柄集合を出力
    for uid in UNIVERSE_IDS:
        subset = universe_df.loc[universe_df["universe_primary"] == uid, ["code"]]
        set_path = sets_dir / f"{uid}.csv"
        try:
            subset.to_csv(set_path, index=False, encoding="utf-8-sig")
        except Exception as e:  # pragma: no cover - I/O 保護
            print(
                f"エラー: universe set の書き込みに失敗しました: {set_path} — {e}",
                file=sys.stderr,
            )
            raise SystemExit(1)

    print(f"master: {master_path}")
    print(f"sets:   {sets_dir}")


if __name__ == "__main__":
    main()

