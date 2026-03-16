"""
論理パス生成（pure）。README の 0011_work / 0012_paid に対応。
全ストレージ Adapter で共通利用する。
"""
from __future__ import annotations

from datetime import date
from typing import Literal

Visibility = Literal["work", "paid"]

# README: 0011_work = 内部用 CSV・中間成果物, 0012_paid = 顧客向け XLSX
WORK_PREFIX = "0011_work"
PAID_PREFIX = "0012_paid"


def build_month_path(run_date: date, visibility: Visibility = "work") -> str:
    """月フォルダの論理パス（末尾 / 付き）。例: 0011_work/2026-03/"""
    prefix = WORK_PREFIX if visibility == "work" else PAID_PREFIX
    return f"{prefix}/{run_date:%Y-%m}/"


def build_day_path(run_date: date, visibility: Visibility = "work") -> str:
    """日フォルダの論理パス（末尾 / 付き）。例: 0011_work/2026-03/2026-03-17/"""
    prefix = WORK_PREFIX if visibility == "work" else PAID_PREFIX
    return f"{prefix}/{run_date:%Y-%m}/{run_date:%Y-%m-%d}/"
