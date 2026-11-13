"""Drive アップロードの一時エラー再試行と上書き契約。"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.gdrive.drive_client import (
    _call_with_retry,
    _is_retryable_drive_error,
    get_or_create_folder,
    upload_file,
)

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status


class _HttpError(Exception):
    def __init__(self, status: int) -> None:
        self.resp = _Resp(status)
        super().__init__(f"http {status}")


class _Request:
    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


class _Files:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def list(self, **kwargs: Any) -> _Request:
        self._state["queries"].append(kwargs.get("q"))

        def _run() -> dict[str, Any]:
            action = self._state["list_script"].pop(0)
            if isinstance(action, Exception):
                raise action
            return {"files": action}

        return _Request(_run)

    def create(self, **kwargs: Any) -> _Request:
        self._state["creates"].append(kwargs.get("body"))

        def _run() -> dict[str, Any]:
            action = self._state["create_script"].pop(0)
            if isinstance(action, Exception):
                raise action
            return action

        return _Request(_run)

    def update(self, **kwargs: Any) -> _Request:
        self._state["updates"].append(kwargs.get("fileId"))

        def _run() -> dict[str, Any]:
            action = self._state["update_script"].pop(0)
            if isinstance(action, Exception):
                raise action
            return action

        return _Request(_run)


class _Service:
    def __init__(self, state: dict[str, Any]) -> None:
        self._files = _Files(state)

    def files(self) -> _Files:
        return self._files


def _state() -> dict[str, Any]:
    return {
        "queries": [],
        "creates": [],
        "updates": [],
        "list_script": [],
        "create_script": [],
        "update_script": [],
    }


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.gdrive.drive_client.time.sleep", lambda _delay: None)
    monkeypatch.setattr(
        "scripts.gdrive.drive_client._DRIVE_RETRY_BACKOFF_SECONDS",
        (0.0, 0.0, 0.0),
    )


def test_502_is_retryable_and_403_is_not() -> None:
    assert _is_retryable_drive_error(_HttpError(502))
    assert _is_retryable_drive_error(_HttpError(429))
    assert _is_retryable_drive_error(ConnectionResetError("reset"))
    assert not _is_retryable_drive_error(_HttpError(403))
    assert not _is_retryable_drive_error(_HttpError(404))


def test_call_with_retry_backs_off_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("scripts.gdrive.drive_client.time.sleep", sleeps.append)
    calls = {"n": 0}

    def _op() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HttpError(502)
        return "ok"

    assert _call_with_retry(_op, what="upload x") == "ok"
    assert sleeps == [5.0, 15.0]


def test_call_with_retry_stops_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.gdrive.drive_client.time.sleep",
        lambda _delay: pytest.fail("403 must not sleep"),
    )

    def _op() -> None:
        raise _HttpError(403)

    with pytest.raises(_HttpError):
        _call_with_retry(_op, what="upload x")


def test_upload_retries_502_then_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_sleep(monkeypatch)
    state = _state()
    state["list_script"] = [[], []]
    state["create_script"] = [_HttpError(502), {"id": "file-1", "webViewLink": "https://example/1"}]
    file_id, link = upload_file(_Service(state), "parent", "a.csv", b"a,b\n", "text/csv")
    assert (file_id, link) == ("file-1", "https://example/1")
    assert len(state["creates"]) == 2
    assert state["updates"] == []


def test_upload_updates_existing_file_instead_of_creating(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_sleep(monkeypatch)
    state = _state()
    state["list_script"] = [[{"id": "existing", "name": "a.csv"}]]
    state["update_script"] = [{"id": "existing", "webViewLink": None}]
    file_id, link = upload_file(_Service(state), "parent", "a.csv", b"a,b\n", "text/csv")
    assert file_id == "existing"
    assert link is None
    assert state["creates"] == []
    assert state["updates"] == ["existing"]
    assert "mimeType != 'application/vnd.google-apps.folder'" in state["queries"][0]


def test_upload_switches_to_update_when_502_left_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """作成はサーバ側で成功し応答だけ 502 だった場合、再試行は新規作成しない。"""
    _no_sleep(monkeypatch)
    state = _state()
    state["list_script"] = [[], [{"id": "created", "name": "a.csv"}]]
    state["create_script"] = [_HttpError(502)]
    state["update_script"] = [{"id": "created", "webViewLink": "https://example/2"}]
    file_id, link = upload_file(_Service(state), "parent", "a.csv", b"a,b\n", "text/csv")
    assert (file_id, link) == ("created", "https://example/2")
    assert len(state["creates"]) == 1
    assert state["updates"] == ["created"]


def test_upload_does_not_retry_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_sleep(monkeypatch)
    state = _state()
    state["list_script"] = [[]]
    state["create_script"] = [_HttpError(403)]
    with pytest.raises(_HttpError):
        upload_file(_Service(state), "parent", "a.csv", b"a,b\n", "text/csv")
    assert len(state["creates"]) == 1


def test_folder_create_retries_502_then_reuses_created_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    state = _state()
    state["list_script"] = [[], [{"id": "folder-1", "name": "2026-11"}]]
    state["create_script"] = [_HttpError(502)]
    folder_id = get_or_create_folder(_Service(state), "parent", "2026-11")
    assert folder_id == "folder-1"
    assert len(state["creates"]) == 1
    assert "mimeType = 'application/vnd.google-apps.folder'" in state["queries"][0]
