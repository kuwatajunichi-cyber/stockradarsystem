"""
コア日次 indicators_YYYYMMDD.csv の探索。

`indicators_event_enriched_*` はファイル名プレフィックスで除外し、急増イベント等の
派生CSVを誤って「最新コア指標」として選ばない。
"""
from __future__ import annotations

import re
from pathlib import Path

from stockradar.config import get_indicators_daily_dir

_CORE_INDICATORS_FILENAME_RE = re.compile(r"^indicators_(\d{8})\.csv$")


def find_latest_core_indicators_csv(base_dir: Path) -> Path | None:
    """
    get_indicators_daily_dir 直下で、ファイル名が indicators_YYYYMMDD.csv に一致するもののうち
    最新（日付文字列最大）を返す。存在しなければ None。
    """
    d = get_indicators_daily_dir(base_dir)
    if not d.is_dir():
        return None
    dated: list[tuple[str, Path]] = []
    for p in d.iterdir():
        if not p.is_file():
            continue
        m = _CORE_INDICATORS_FILENAME_RE.match(p.name)
        if m:
            dated.append((m.group(1), p))
    if not dated:
        return None
    dated.sort(key=lambda x: x[0])
    return dated[-1][1]
