import subprocess
from unittest.mock import patch

import pytest

from stockradar.jobs import cache_ops
from stockradar.jobs.cache_ops import should_rotate_cache


def test_should_rotate_cache() -> None:
    assert should_rotate_cache(is_replay=False, job_success=True) is True
    assert should_rotate_cache(is_replay=True, job_success=True) is False
    assert should_rotate_cache(is_replay=False, job_success=False) is False


def test_main_rotate_delete_skips_on_replay() -> None:
    calls: list[tuple[str, str]] = []

    def fake_delete(repo: str, key: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((repo, key))
        return subprocess.CompletedProcess(["gh"], 0, stdout="", stderr="")

    with patch.object(cache_ops, "gh_cache_delete", fake_delete):
        with pytest.raises(SystemExit) as exc:
            cache_ops.main(
                [
                    "rotate-delete",
                    "--repo",
                    "owner/name",
                    "--key",
                    "k1",
                    "--is-replay",
                    "true",
                ]
            )
        assert exc.value.code == 0
    assert calls == []


def test_main_rotate_delete_invokes_gh_when_not_replay() -> None:
    calls: list[tuple[str, str]] = []

    def fake_delete(repo: str, key: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((repo, key))
        return subprocess.CompletedProcess(["gh"], 0, stdout="", stderr="")

    with patch.object(cache_ops, "gh_cache_delete", fake_delete):
        with pytest.raises(SystemExit) as exc:
            cache_ops.main(
                [
                    "rotate-delete",
                    "--repo",
                    "owner/name",
                    "--key",
                    "k1",
                    "--is-replay",
                    "false",
                ]
            )
        assert exc.value.code == 0
    assert calls == [("owner/name", "k1")]


def test_main_delete_key_invokes_gh() -> None:
    calls: list[tuple[str, str]] = []

    def fake_delete(repo: str, key: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((repo, key))
        return subprocess.CompletedProcess(["gh"], 0, stdout="", stderr="")

    with patch.object(cache_ops, "gh_cache_delete", fake_delete):
        with pytest.raises(SystemExit) as exc:
            cache_ops.main(["delete-key", "--repo", "owner/name", "--key", "k1"])
        assert exc.value.code == 0
    assert calls == [("owner/name", "k1")]