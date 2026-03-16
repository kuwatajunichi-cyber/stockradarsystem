"""scripts.storage.paths の論理パス生成が README 想定と一致することを検証する。"""
from __future__ import annotations

from datetime import date

import pytest

# プロジェクトルートを path に追加
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.storage.paths import (
    PAID_PREFIX,
    WORK_PREFIX,
    build_day_path,
    build_month_path,
)


def test_work_paid_prefix() -> None:
    assert WORK_PREFIX == "0011_work"
    assert PAID_PREFIX == "0012_paid"


def test_build_month_path_work() -> None:
    d = date(2026, 3, 17)
    assert build_month_path(d, "work") == "0011_work/2026-03/"


def test_build_month_path_paid() -> None:
    d = date(2026, 3, 17)
    assert build_month_path(d, "paid") == "0012_paid/2026-03/"


def test_build_day_path_work() -> None:
    d = date(2026, 3, 17)
    assert build_day_path(d, "work") == "0011_work/2026-03/2026-03-17/"


def test_build_day_path_paid() -> None:
    d = date(2026, 3, 17)
    assert build_day_path(d, "paid") == "0012_paid/2026-03/2026-03-17/"


def test_paths_end_with_slash() -> None:
    d = date(2025, 12, 1)
    assert build_month_path(d, "work").endswith("/")
    assert build_day_path(d, "work").endswith("/")
