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


def test_drive_uses_work_paid_routing_and_mime(monkeypatch) -> None:
    csv_path = _tmp_file(".csv", b"a,b\n1,2\n")
    xlsx_path = _tmp_file(".xlsx", b"PK\x03\x04dummy")

    class _FakeDriveAdapter:
        def __init__(self) -> None:
            self.created: list[tuple[str, str]] = []
            self.uploaded: list[tuple[str, str, str]] = []

        def get_or_create_folder(self, parent_id: str, name: str) -> str:
            self.created.append((parent_id, name))
            return f"{parent_id}/{name}"

        def upload_file(self, parent_id: str, name: str, content: bytes, mime_type: str):
            self.uploaded.append((parent_id, name, mime_type))
            return ("file-id", None)

    adapter = _FakeDriveAdapter()

    monkeypatch.setattr("scripts.gdrive.drive_client.get_credentials", lambda: object())
    monkeypatch.setattr("scripts.gdrive.drive_client.build_service", lambda _creds: object())
    monkeypatch.setattr("scripts.gdrive.drive_client.GoogleDriveAdapter", lambda _svc: adapter)
    monkeypatch.setattr("scripts.gdrive.drive_client.get_folder_id_work", lambda: "WORK_ROOT")
    monkeypatch.setattr("scripts.gdrive.drive_client.get_folder_id_paid", lambda: "PAID_ROOT")

    code = run("2026-04-01", [csv_path, xlsx_path], {"drive"})
    assert code == 0

    assert ("WORK_ROOT", "2026-04") in adapter.created
    assert ("WORK_ROOT/2026-04", "2026-04-01") in adapter.created
    assert ("PAID_ROOT", "2026-04") in adapter.created

    assert any(
        name == csv_path.name
        and parent_id == "WORK_ROOT/2026-04/2026-04-01"
        and mime_type == "text/csv"
        for parent_id, name, mime_type in adapter.uploaded
    )
    assert any(
        name == xlsx_path.name
        and parent_id == "PAID_ROOT/2026-04"
        and mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        for parent_id, name, mime_type in adapter.uploaded
    )
