"""
equity_domestic を ipo / illiquid / core に二次分割するジョブ。
入力: equity_domestic.csv と data/cache/yf_daily/（キャッシュ＋manifest）
出力: data/universe/jpx/sets_secondary_YYYYMMDD/
  - equity_domestic_ipo.csv, equity_domestic_illiquid.csv, equity_domestic_core.csv（code のみ）
  - equity_domestic_ipo_with_name.csv 等（code, name）。銘柄名は JPX processed CSV をマスタとする。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from stockradar.config import (
    get_ipo_lookback_days,
    get_liq_lookback_days,
    get_liq_min_median_turnover_yen,
    get_yf_daily_cache_dir,
)
from stockradar.universe.equity_secondary import (
    split_equity_domestic_secondary,
)
from stockradar.universe.jpx_primary import _normalize_code

MANIFEST_FILENAME = "_manifest.jsonl"


def _find_latest_equity_domestic(base_dir: Path) -> Path | None:
    """data/universe/jpx/sets_YYYYMMDD/equity_domestic.csv の最新を返す。"""
    jpx_dir = base_dir / "data" / "universe" / "jpx"
    if not jpx_dir.exists():
        return None
    candidates = []
    for d in jpx_dir.iterdir():
        if d.is_dir() and re.match(r"sets_\d{8}", d.name):
            p = d / "equity_domestic.csv"
            if p.exists():
                candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name)
    return candidates[-1]


def _infer_ymd_from_path(path: Path) -> str | None:
    """sets_YYYYMMDD または 含まれる YYYYMMDD を抽出。"""
    m = re.search(r"(\d{8})", path.as_posix())
    return m.group(1) if m else None


def _load_code_to_name_from_jpx_processed(base_dir: Path, ymd: str) -> dict[str, str] | None:
    """
    JPX processed CSV（data/processed/jpx/jpx_list_YYYYMMDD.csv）から
    コード → 銘柄名 のマッピングを返す。ファイルが無い場合は None。
    """
    path = base_dir / "data" / "processed" / "jpx" / f"jpx_list_{ymd}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if "コード" not in df.columns or "銘柄名" not in df.columns:
        return None
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        code = _normalize_code(row.get("コード"))
        if not code:
            continue
        name = row.get("銘柄名")
        if pd.isna(name):
            name = ""
        else:
            name = str(name).strip()
        out[code] = name
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Split equity_domestic into ipo / illiquid / core."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="equity_domestic.csv のパス（省略時は最新 sets_YYYYMMDD から自動選択）",
    )
    args = parser.parse_args(argv)

    base = Path.cwd()
    cache_dir = get_yf_daily_cache_dir(base)
    manifest_path = cache_dir / MANIFEST_FILENAME

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = base / input_path
    else:
        input_path = _find_latest_equity_domestic(base)
        if input_path is None:
            print(
                "エラー: equity_domestic.csv が見つかりません。"
                "data/universe/jpx/sets_YYYYMMDD/equity_domestic.csv を用意するか --input で指定してください。",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if not input_path.exists():
        print(f"エラー: 入力が存在しません: {input_path}", file=sys.stderr)
        raise SystemExit(1)

    print(f"キャッシュ参照: {cache_dir} (manifest={manifest_path.name})", file=sys.stderr)
    if not manifest_path.exists():
        print(
            "注意: キャッシュの manifest がありません。先に以下を実行してください（プロジェクトルートで）。",
            file=sys.stderr,
        )
        print(
            "  python -m stockradar.jobs.fetch_yf_daily_for_universe --input data/universe/jpx/sets_YYYYMMDD/equity_domestic.csv",
            file=sys.stderr,
        )
        print(
            "取得完了まで待ってから、本ジョブを再実行してください。全銘柄は ipo に分類されます。",
            file=sys.stderr,
        )

    try:
        liq_min = get_liq_min_median_turnover_yen()
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        raise SystemExit(1)

    df = pd.read_csv(input_path)
    if "code" not in df.columns:
        print("エラー: 入力CSVに code 列がありません。", file=sys.stderr)
        raise SystemExit(1)
    codes = [str(c).strip() for c in df["code"].dropna() if str(c).strip()]

    ipo_days = get_ipo_lookback_days()
    liq_days = get_liq_lookback_days()

    result = split_equity_domestic_secondary(
        codes=codes,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        ipo_lookback_days=ipo_days,
        liq_lookback_days=liq_days,
        liq_min_median_turnover_yen=liq_min,
    )

    ymd = _infer_ymd_from_path(input_path) or "00000000"
    out_dir = base / "data" / "universe" / "jpx" / f"sets_secondary_{ymd}"
    out_dir.mkdir(parents=True, exist_ok=True)

    code_to_name = _load_code_to_name_from_jpx_processed(base, ymd)
    if code_to_name is None:
        print(
            f"注意: JPX processed CSV が見つかりません（data/processed/jpx/jpx_list_{ymd}.csv）。"
            "銘柄名付きCSVは出力しません。",
            file=sys.stderr,
        )

    for name, code_list in [
        ("equity_domestic_ipo", result.ipo),
        ("equity_domestic_illiquid", result.illiquid),
        ("equity_domestic_core", result.core),
    ]:
        path = out_dir / f"{name}.csv"
        pd.DataFrame({"code": code_list}).to_csv(path, index=False, encoding="utf-8-sig")
        if code_to_name is not None:
            names = [code_to_name.get(c, "") for c in code_list]
            path_with_name = out_dir / f"{name}_with_name.csv"
            pd.DataFrame({"code": code_list, "name": names}).to_csv(
                path_with_name, index=False, encoding="utf-8-sig"
            )

    s = result.summary
    print("--- ログサマリ ---", file=sys.stderr)
    print(f"対象銘柄数: {s['total']}", file=sys.stderr)
    print(f"取得ok: {s['fetch_ok']}  取得失敗: {s['fetch_failed']}  bars不足: {s['bars_insufficient']}", file=sys.stderr)
    print(f"分割結果  ipo: {s['ipo_count']}  illiquid: {s['illiquid_count']}  core: {s['core_count']}", file=sys.stderr)
    print(f"illiquid 判定  期間(営業日): {s['liq_lookback_days']}  閾値(円): {s['liq_min_median_turnover_yen']}", file=sys.stderr)
    print(f"出力: {out_dir}", file=sys.stderr)
    print(out_dir)

if __name__ == "__main__":
    main()
