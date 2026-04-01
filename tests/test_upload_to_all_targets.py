from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.upload_to_all_targets import run


def _tmp_file(suffix: str, content: bytes = b"x") -> Path:
    fd, path_str = tempfile.mkstemp(suffix=suffix)
    path = Path(path_str)
    path.write_bytes(content)
    return path


def test_run_returns_zero_when_dropbox_fails(monkeypatch) -> None:
    csv_path = _tmp_file(".csv", b"a,b\n1,2\n")

    class _FailDropboxAdapter:
        def upload_file(self, path: str, name: str, content: bytes, mime_type: str) -> str:
            raise RuntimeError("dropbox down")

    monkeypatch.setattr(
        "scripts.storage.dropbox_client.DropboxStorageAdapter",
        lambda: _FailDropboxAdapter(),
    )

    code = run("2026-04-01", [csv_path], {"dropbox"})
    assert code == 0


def test_run_returns_zero_when_github_upload_fails(monkeypatch) -> None:
    csv_path = _tmp_file(".csv", b"a,b\n1,2\n")

    class _Proc:
        def __init__(self, returncode: int = 0, stderr: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr

    def _fake_subprocess_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        cmd = args[0]
        if cmd[:3] == ["gh", "release", "view"]:
            return _Proc(returncode=0)
        if cmd[:3] == ["gh", "release", "upload"]:
            import subprocess

            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="403 forbidden")
        return _Proc(returncode=0)

    monkeypatch.setattr("subprocess.run", _fake_subprocess_run)

    code = run("2026-04-01", [csv_path], {"github"})
    assert code == 0
