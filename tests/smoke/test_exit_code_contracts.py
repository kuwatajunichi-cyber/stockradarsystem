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


def test_run_monthly_missing_three_csv_exits_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job_calls: list[str] = []

    def _run_job(module: str, args: list[str] | None = None) -> tuple[int, str]:
        job_calls.append(module)
        return (0, "ok")

    monkeypatch.setattr(run_monthly, "RUN_ID", "test-run")
    monkeypatch.setattr(run_monthly, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(run_monthly, "LATEST_DIR", tmp_path / "latest")
    monkeypatch.setattr(run_monthly, "LATEST_POINTER", (tmp_path / "latest" / "LATEST_RUN_ID.txt"))
    monkeypatch.setattr(run_monthly, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(run_monthly, "run_job", _run_job)
    monkeypatch.setattr(run_monthly, "find_latest_secondary_outputs", lambda: ({}, ["missing"]))

    with pytest.raises(SystemExit) as e:
        run_monthly.main()
    assert e.value.code == run_monthly.EXIT_CONTRACT
    assert len(job_calls) == 5
    assert job_calls[0] == "stockradar.jobs.update_jpx_url_cache"
    assert job_calls[-1] == "stockradar.jobs.split_equity_domestic_secondary"


def test_run_monthly_init_failure_exits_runtime_without_run_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    staging_path = tmp_path / "staging"
    staging_path.write_bytes(b"x")

    def _no_run_job(*_args: object, **_kwargs: object) -> tuple[int, str]:
        raise AssertionError("run_job must not run when init fails")

    monkeypatch.setattr(run_monthly, "RUN_ID", "test-run")
    monkeypatch.setattr(run_monthly, "STAGING_DIR", staging_path)
    monkeypatch.setattr(run_monthly, "LATEST_DIR", tmp_path / "latest")
    monkeypatch.setattr(run_monthly, "LATEST_POINTER", tmp_path / "latest" / "LATEST_RUN_ID.txt")
    monkeypatch.setattr(run_monthly, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(run_monthly, "run_job", _no_run_job)

    with pytest.raises(SystemExit) as e:
        run_monthly.main()
    assert e.value.code == run_monthly.EXIT_RUNTIME


def _monthly_gate_csv_bytes() -> bytes:
    """verify_gate: code,name 先頭・ヘッダ除く10行以上・非ゼロサイズ。"""
    lines = ["code,name,x_col"] + [f"{8000 + i},N{i},0" for i in range(11)]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def test_run_monthly_happy_path_updates_latest_pointer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """5ジョブ成功後、verify_gate 準拠の3CSVを staging に書き、LATEST_POINTER を更新する。"""
    src_dir = tmp_path / "secondary"
    src_dir.mkdir(parents=True, exist_ok=True)
    body = _monthly_gate_csv_bytes()
    outputs: dict[str, Path] = {}
    for name in run_monthly.LATEST_3CSV:
        p = src_dir / name
        p.write_bytes(body)
        outputs[name] = p

    job_calls: list[str] = []

    def _run_job_ok(module: str, args: list[str] | None = None) -> tuple[int, str]:
        job_calls.append(module)
        return (0, "ok")

    monkeypatch.setattr(run_monthly, "RUN_ID", "test-run-happy")
    monkeypatch.setattr(run_monthly, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(run_monthly, "LATEST_DIR", tmp_path / "latest")
    monkeypatch.setattr(run_monthly, "LATEST_POINTER", tmp_path / "latest" / "LATEST_RUN_ID.txt")
    monkeypatch.setattr(run_monthly, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(run_monthly, "run_job", _run_job_ok)
    monkeypatch.setattr(run_monthly, "find_latest_secondary_outputs", lambda: (outputs, []))

    run_monthly.main()

    assert job_calls == [
        "stockradar.jobs.update_jpx_url_cache",
        "stockradar.jobs.fetch_jpx_list",
        "stockradar.jobs.build_universe_from_jpx",
        "stockradar.jobs.fetch_yf_daily_for_universe",
        "stockradar.jobs.split_equity_domestic_secondary",
    ]
    assert run_monthly.LATEST_POINTER.read_text(encoding="utf-8") == "test-run-happy"
    for name in run_monthly.LATEST_3CSV:
        assert (run_monthly.STAGING_DIR / name).exists()
        assert (run_monthly.STAGING_DIR / f"{name}.manifest.json").exists()


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
