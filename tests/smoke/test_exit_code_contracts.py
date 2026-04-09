from __future__ import annotations

import subprocess
import sys
import importlib.util
from pathlib import Path

import pytest

_RUN_MONTHLY_PATH = Path("scripts/run_monthly.py").resolve()
_SPEC = importlib.util.spec_from_file_location("run_monthly_module", _RUN_MONTHLY_PATH)
assert _SPEC and _SPEC.loader
run_monthly = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_monthly)


pytestmark = pytest.mark.smoke


def _run_job_exit_code(module: str, args: list[str]) -> int:
    result = subprocess.run(
        [sys.executable, "-m", module] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return result.returncode


def test_job_invalid_run_date_exit_code_1() -> None:
    assert _run_job_exit_code("stockradar.jobs.ensure_index_cache", ["--run-date", "2026-99-99"]) == 1
    assert _run_job_exit_code("stockradar.jobs.ensure_core_cache", ["--run-date", "invalid"]) == 1
    assert _run_job_exit_code("stockradar.jobs.compute_indicators_for_core", ["--run-date", "bad-date"]) == 1


def test_run_monthly_contract_violation_detected_by_gate(tmp_path: Path) -> None:
    ok, errors = run_monthly.verify_gate(tmp_path)
    assert ok is False
    assert len(errors) > 0


def test_run_monthly_contract_violation_exits_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_monthly, "RUN_ID", "test-run")
    monkeypatch.setattr(run_monthly, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(run_monthly, "LATEST_DIR", tmp_path / "latest")
    monkeypatch.setattr(run_monthly, "LATEST_POINTER", (tmp_path / "latest" / "LATEST_RUN_ID.txt"))
    monkeypatch.setattr(run_monthly, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(run_monthly, "run_job", lambda *_args, **_kwargs: (0, "ok"))
    monkeypatch.setattr(run_monthly, "find_latest_secondary_outputs", lambda: ({}, ["missing"]))

    with pytest.raises(SystemExit) as e:
        run_monthly.main()
    assert e.value.code == 2


def test_run_monthly_runtime_failure_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_monthly, "RUN_ID", "test-run")
    monkeypatch.setattr(run_monthly, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(run_monthly, "LATEST_DIR", tmp_path / "latest")
    monkeypatch.setattr(run_monthly, "LATEST_POINTER", (tmp_path / "latest" / "LATEST_RUN_ID.txt"))
    monkeypatch.setattr(run_monthly, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(run_monthly, "run_job", lambda *_args, **_kwargs: (2, "runtime error"))

    with pytest.raises(SystemExit) as e:
        run_monthly.main()
    assert e.value.code == 2
