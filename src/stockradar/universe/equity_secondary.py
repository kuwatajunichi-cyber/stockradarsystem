"""
equity_domestic を ipo / illiquid / core に二次分割する判定ロジック。
判定は設定（閾値・日数）で駆動し、将来 price/mcap 等を追加しやすい形に分離する。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class SecondarySplitResult:
    """二次分割の結果とログ用サマリ。"""

    ipo: list[str]
    illiquid: list[str]
    core: list[str]
    summary: dict


def _load_manifest_entries(manifest_path: Path) -> dict[str, dict]:
    """ユニバース用 manifest JSONL を読んで code -> エントリ（code 無し行は symbol を鍵に）。"""
    import json

    out: dict[str, dict] = {}
    if not manifest_path.exists():
        return out
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ent = json.loads(line)
                code = ent.get("code") or ent.get("symbol")
                if code:
                    out[str(code).strip()] = ent
            except json.JSONDecodeError:
                continue
    return out


def _median_turnover_yen(cache_path: Path, lookback_days: int) -> float | None:
    """
    キャッシュCSV（Close, Volume）から直近 lookback_days の
    売買代金近似 median(Close * Volume) を返す。失敗・不足時は None。
    """
    if not cache_path.exists():
        return None
    try:
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    except Exception:
        return None
    if "Close" not in df.columns or "Volume" not in df.columns:
        return None
    df = df.sort_index()
    if len(df) < lookback_days:
        return None
    tail = df.tail(lookback_days)
    turnover = tail["Close"] * tail["Volume"]
    return float(turnover.median())


def split_equity_domestic_secondary(
    codes: list[str],
    cache_dir: Path,
    manifest_path: Path,
    ipo_lookback_days: int,
    liq_lookback_days: int,
    liq_min_median_turnover_yen: float,
) -> SecondarySplitResult:
    """
    equity_domestic の code リストを ipo / illiquid / core に排他分類する。

    - ipo: 取得失敗 or fetched_bars < ipo_lookback_days（insufficient_history 含む）
    - illiquid: 上記以外で median(turnover_yen) < liq_min_median_turnover_yen
    - core: 残り

    戻り値: SecondarySplitResult（ipo/illiquid/core の code リストと summary）。
    """
    manifest = _load_manifest_entries(manifest_path)
    ipo: list[str] = []
    illiquid: list[str] = []
    core: list[str] = []

    n_ok = 0
    n_failed = 0
    n_insufficient_bars = 0
    n_stale_run_date = 0

    for code in codes:
        ent = manifest.get(code)
        status = ent.get("status", "missing") if ent else "missing"
        fetched_bars = ent.get("fetched_bars", 0) if ent else 0

        if status == "failed" or status == "missing":
            n_failed += 1
            ipo.append(code)
            continue
        # 日次 manifest の stale（run_date 当日バー未到達）と区別: ユニバース取得では基本発生しないが、
        # 将来の混読に備え、本数が IPO 十分なら IPO に寄せず流動性判定へ回す。
        if status == "stale" and fetched_bars >= ipo_lookback_days:
            n_stale_run_date += 1
            n_ok += 1
        elif status != "ok" or fetched_bars < ipo_lookback_days:
            # insufficient / failed 以外の不足・本数不足 → ipo 寄せ
            n_insufficient_bars += 1
            ipo.append(code)
            continue
        else:
            n_ok += 1

        # IPO でない → illiquid 判定
        csv_path = cache_dir / f"{code}.csv"
        median_turnover = _median_turnover_yen(csv_path, liq_lookback_days)
        if median_turnover is None or median_turnover < liq_min_median_turnover_yen:
            illiquid.append(code)
        else:
            core.append(code)

    summary = {
        "total": len(codes),
        "fetch_ok": n_ok,
        "fetch_failed": n_failed,
        "bars_insufficient": n_insufficient_bars,
        "n_stale_run_date": n_stale_run_date,
        "ipo_count": len(ipo),
        "illiquid_count": len(illiquid),
        "core_count": len(core),
        "ipo_lookback_days": ipo_lookback_days,
        "liq_lookback_days": liq_lookback_days,
        "liq_min_median_turnover_yen": liq_min_median_turnover_yen,
    }
    return SecondarySplitResult(ipo=ipo, illiquid=illiquid, core=core, summary=summary)
