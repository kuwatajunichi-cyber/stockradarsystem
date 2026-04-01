from __future__ import annotations

import pytest

from scripts.storage.dropbox_client import DropboxStorageAdapter


class _FakeResponse:
    def __init__(self, status_code: int, text: str, json_data: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        raise RuntimeError(f"http_error:{self.status_code}")


def test_dropbox_upload_file_retries_on_429_then_succeeds(monkeypatch) -> None:
    adapter = DropboxStorageAdapter(
        app_key="k",
        app_secret="s",
        refresh_token="r",
        base_folder="",
    )
    adapter._access_token = "dummy-token"

    responses = [
        _FakeResponse(429, "too_many_write_operations", { "error": {"retry_after": 1} }),
        _FakeResponse(200, "ok", {}),
    ]
    sleep_calls: list[int] = []

    def _fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        return responses.pop(0)

    def _fake_sleep(sec: int) -> None:
        sleep_calls.append(sec)

    monkeypatch.setattr("requests.post", _fake_post)
    monkeypatch.setattr("scripts.storage.dropbox_client.time.sleep", _fake_sleep)

    full_path = adapter.upload_file("0011_work/2026-04/2026-04-01/", "a.csv", b"1,2,3\n")
    assert full_path == "/011_work/2026-04/2026-04-01/a.csv"
    assert sleep_calls == [1]


def test_dropbox_upload_file_raises_after_retry_exhaust(monkeypatch) -> None:
    adapter = DropboxStorageAdapter(
        app_key="k",
        app_secret="s",
        refresh_token="r",
        base_folder="",
    )
    adapter._access_token = "dummy-token"

    responses = [
        _FakeResponse(429, "too_many_write_operations", {"error": {"retry_after": 1}}),
        _FakeResponse(429, "too_many_write_operations", {"error": {"retry_after": 1}}),
        _FakeResponse(429, "too_many_write_operations", {"error": {"retry_after": 1}}),
        _FakeResponse(429, "too_many_write_operations", {"error": {"retry_after": 1}}),
    ]

    def _fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        return responses.pop(0)

    monkeypatch.setattr("requests.post", _fake_post)
    monkeypatch.setattr("scripts.storage.dropbox_client.time.sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="http_error:429"):
        adapter.upload_file("0011_work/2026-04/2026-04-01/", "a.csv", b"1,2,3\n")
