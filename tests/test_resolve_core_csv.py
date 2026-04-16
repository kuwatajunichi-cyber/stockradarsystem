from __future__ import annotations

import json
import re
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from stockradar.jobs import resolve_core_csv as mod
from stockradar.jobs.patch_universe_daily import MANIFEST_FILENAME as PATCH_MANIFEST_NAME
from stockradar.jobs.resolve_core_csv import CORE_CSV_NAME, QUALITY_JSON_NAME, STATE_FILENAME


@pytest.fixture
def tags_file(tmp_path: Path) -> Path:
    p = tmp_path / "tags.txt"
    p.write_text("monthly-20260207-1\nmonthly-20260101-1\n", encoding="utf-8")
    return p


def test_list_action_cache_keys_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "gh"
        page_part = [x for x in cmd if "page=" in x][0]
        # Avoid matching per_page=100 as page=100
        m = re.search(r"[?&]page=(\d+)", page_part)
        assert m is not None, page_part
        page_n = int(m.group(1))
        if page_n == 1:
            caches = [{"key": f"k{i}"} for i in range(100)]
            calls.append(1)
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"actions_caches": caches}), stderr=""
            )
        if page_n == 2:
            caches = [{"key": "last"}]
            calls.append(2)
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"actions_caches": caches}), stderr=""
            )
        raise AssertionError(page_part)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    keys = mod.list_action_cache_keys("o/r")
    assert keys[0] == "k0" and keys[-1] == "last"
    assert len(keys) == 101
    assert calls == [1, 2]


def test_list_action_cache_keys_gh_failure_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            ["gh"], 1, stdout="", stderr="boom"
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as exc:
        mod.list_action_cache_keys("o/r")
    assert exc.value.code == 1


def test_run_select_warns_on_unparseable_prefix(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, tags_file: Path
) -> None:
    state_path = tmp_path / STATE_FILENAME

    def keys(_repo: str) -> list[str]:
        return [
            "universe-patched-bad-no-date",
            "universe-patched-monthly-20260207-1-2026-04-10",
        ]

    args = Namespace(
        repo="o/r",
        run_date="2026-04-15",
        tags_file=tags_file,
        state_path=state_path,
    )
    mod.run_select(args, list_cache_keys=keys)
    err = capsys.readouterr().err
    assert "warning:" in err
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["patched_cache_key"] == "universe-patched-monthly-20260207-1-2026-04-10"


def test_run_select_no_patched_candidate(tmp_path: Path, tags_file: Path) -> None:
    state_path = tmp_path / STATE_FILENAME
    args = Namespace(
        repo="o/r",
        run_date="2026-04-15",
        tags_file=tags_file,
        state_path=state_path,
    )
    mod.run_select(args, list_cache_keys=lambda _r: ["unrelated-key"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["patched_cache_key"] is None


def test_run_materialize_patched_ok(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    patched = tmp_path / "patched"
    staging.mkdir()
    patched.mkdir()
    monthly = "monthly-20260207-1"
    key = f"universe-patched-{monthly}-2026-04-10"
    (staging / STATE_FILENAME).write_text(
        json.dumps(
            {
                "monthly_tag": monthly,
                "universe_resolution": "time_series_ok",
                "resolution_reason": "",
                "run_date": "2026-04-15",
                "patched_cache_key": key,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patched / CORE_CSV_NAME).write_text("code,name\n1,Test\n", encoding="utf-8")
    (patched / PATCH_MANIFEST_NAME).write_text(
        json.dumps({"chosen_monthly_tag": monthly}),
        encoding="utf-8",
    )
    args = Namespace(repo="o/r", staging_dir=staging, patched_dir=patched)
    mod.run_materialize(args)
    q = json.loads((staging / QUALITY_JSON_NAME).read_text(encoding="utf-8"))
    assert q["core_source"] == "patched_cache"
    assert q["delisted_patch_applied"] is True
    assert q["selected_cache_key"] == key
    assert q["quality_tier"] == "full"
    assert (staging / CORE_CSV_NAME).read_text(encoding="utf-8").startswith("code,name")


def test_run_materialize_manifest_mismatch_exits(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    patched = tmp_path / "patched"
    staging.mkdir()
    patched.mkdir()
    monthly = "monthly-20260207-1"
    (staging / STATE_FILENAME).write_text(
        json.dumps(
            {
                "monthly_tag": monthly,
                "universe_resolution": "time_series_ok",
                "resolution_reason": "",
                "run_date": "2026-04-15",
                "patched_cache_key": "universe-patched-monthly-20260207-1-2026-04-10",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patched / CORE_CSV_NAME).write_text("x\n", encoding="utf-8")
    (patched / PATCH_MANIFEST_NAME).write_text(
        json.dumps({"chosen_monthly_tag": "other-tag"}),
        encoding="utf-8",
    )
    args = Namespace(repo="o/r", staging_dir=staging, patched_dir=patched)
    with pytest.raises(SystemExit) as exc:
        mod.run_materialize(args)
    assert exc.value.code == 1


def test_run_materialize_monthly_fallback_uses_fake_gh(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    patched = tmp_path / "patched"
    staging.mkdir()
    patched.mkdir()
    monthly = "monthly-20260207-1"
    (staging / STATE_FILENAME).write_text(
        json.dumps(
            {
                "monthly_tag": monthly,
                "universe_resolution": "time_series_ok",
                "resolution_reason": "",
                "run_date": "2026-04-15",
                "patched_cache_key": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_dl(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        i = cmd.index("--dir")
        d = Path(cmd[i + 1])
        d.mkdir(parents=True, exist_ok=True)
        (d / CORE_CSV_NAME).write_text("a,b\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    args = Namespace(repo="o/r", staging_dir=staging, patched_dir=patched)
    mod.run_materialize(args, gh_release_download=fake_dl)
    q = json.loads((staging / QUALITY_JSON_NAME).read_text(encoding="utf-8"))
    assert q["core_source"] == "monthly_fallback"
    assert q["delisted_patch_applied"] is False
    assert q["selected_cache_key"] is None
    assert q["quality_tier"] == "degraded_without_delisted_patch"