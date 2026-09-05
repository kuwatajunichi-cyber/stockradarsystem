"""Healthchecks.io success ping. Fail closed on empty URL or HTTP error.

Does not log the ping URL (Secret). continue-on-error belongs on the GHA step, not here.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

PING_URL_ENV = "HEALTHCHECKS_PING_URL"
ATTEMPTS = 3
TIMEOUT_SEC = 10.0


class HeartbeatError(Exception):
    """Ping URL missing or request failed. Message must not include the URL."""


def ping_healthcheck(
    url: str,
    *,
    urlopen: Callable[..., Any] | None = None,
    attempts: int = ATTEMPTS,
    timeout_sec: float = TIMEOUT_SEC,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    cleaned = (url or "").strip()
    if not cleaned:
        raise HeartbeatError("ping URL is empty")
    last_exc: BaseException | None = None
    for index in range(attempts):
        try:
            request = urllib.request.Request(cleaned, method="GET")
            with opener(request, timeout=timeout_sec) as response:
                code = getattr(response, "status", None)
                if code is None:
                    code = response.getcode()
                if int(code) >= 400:
                    raise HeartbeatError(f"HTTP {code}")
            return
        except HeartbeatError:
            raise
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:
            last_exc = exc
            if index + 1 < attempts:
                sleep_fn(0.5)
    raise HeartbeatError("request failed") from last_exc


def _append_step_summary(ok: bool) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    line = f"- heartbeat_ok: `{'true' if ok else 'false'}`\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)


def main(argv: list[str] | None = None) -> int:
    del argv
    url = os.environ.get(PING_URL_ENV, "")
    try:
        ping_healthcheck(url)
    except HeartbeatError as exc:
        print(f"heartbeat_ok=false error={exc}", file=sys.stderr)
        _append_step_summary(False)
        return 1
    print("heartbeat_ok=true")
    _append_step_summary(True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
