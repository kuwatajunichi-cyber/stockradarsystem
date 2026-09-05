"""Unit tests for Healthchecks heartbeat (Secrets-free, Fake HTTP)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.observability.healthchecks_heartbeat import (
    PING_URL_ENV,
    HeartbeatError,
    main,
    ping_healthcheck,
)


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.unit
def test_empty_url_fails_closed() -> None:
    with pytest.raises(HeartbeatError, match="empty"):
        ping_healthcheck("")
    with pytest.raises(HeartbeatError, match="empty"):
        ping_healthcheck("   ")


@pytest.mark.unit
def test_success_does_not_retry() -> None:
    calls = {"n": 0}

    def urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        calls["n"] += 1
        return _FakeResponse(200)

    ping_healthcheck(
        "https://hc-ping.com/example",
        urlopen=urlopen,
        sleep_fn=lambda _s: None,
    )
    assert calls["n"] == 1


@pytest.mark.unit
def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return _FakeResponse(200)

    ping_healthcheck(
        "https://hc-ping.com/example",
        urlopen=urlopen,
        sleep_fn=lambda _s: None,
    )
    assert calls["n"] == 3


@pytest.mark.unit
def test_http_error_does_not_include_url() -> None:
    def urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(500)

    with pytest.raises(HeartbeatError) as excinfo:
        ping_healthcheck(
            "https://hc-ping.com/secret-uuid",
            urlopen=urlopen,
            sleep_fn=lambda _s: None,
        )
    assert "secret-uuid" not in str(excinfo.value)
    assert "hc-ping.com" not in str(excinfo.value)


@pytest.mark.unit
def test_main_empty_env_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.delenv(PING_URL_ENV, raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main([]) == 1
    assert "heartbeat_ok: `false`" in summary.read_text(encoding="utf-8")


@pytest.mark.unit
def test_main_success_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv(PING_URL_ENV, "https://hc-ping.com/example")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(200)

    monkeypatch.setattr(
        "stockradar.observability.healthchecks_heartbeat.urllib.request.urlopen",
        urlopen,
    )
    assert main([]) == 0
    assert "heartbeat_ok: `true`" in summary.read_text(encoding="utf-8")
