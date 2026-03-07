"""ジョブCLIの --run-date 異常値時のバリデーションテスト。

外部I/Oは発生しない（パース段階で終了するため）。
"""
from __future__ import annotations

import subprocess
import sys


def _run_job_exit_code(module: str, args: list[str]) -> tuple[int, str]:
    """ジョブを実行し (exit_code, stderr) を返す。"""
    result = subprocess.run(
        [sys.executable, "-m", module] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )
    return result.returncode, (result.stderr or "") + (result.stdout or "")


def test_ensure_index_cache_invalid_run_date_exits_1() -> None:
    """ensure_index_cache: 不正な --run-date で終了コード 1。"""
    code, _ = _run_job_exit_code(
        "stockradar.jobs.ensure_index_cache",
        ["--run-date", "2026-02-99"],
    )
    assert code == 1


def test_ensure_core_cache_invalid_run_date_exits_1() -> None:
    """ensure_core_cache: 不正な --run-date で終了コード 1。"""
    code, _ = _run_job_exit_code(
        "stockradar.jobs.ensure_core_cache",
        ["--run-date", "invalid"],
    )
    assert code == 1


def test_compute_indicators_invalid_run_date_exits_1() -> None:
    """compute_indicators_for_core: 不正な --run-date で終了コード 1。"""
    code, _ = _run_job_exit_code(
        "stockradar.jobs.compute_indicators_for_core",
        ["--run-date", "not-a-date"],
    )
    assert code == 1


def test_patch_universe_daily_invalid_run_date_exits_1() -> None:
    """patch_universe_daily: 不正な --run-date で終了コード 1。"""
    code, _ = _run_job_exit_code(
        "stockradar.jobs.patch_universe_daily",
        ["--run-date", "2026/02/11", "--input", "dummy.csv"],
    )
    assert code == 1
