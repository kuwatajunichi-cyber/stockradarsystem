"""Deploy web-ui-static login shell. Does not print secrets."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CONFIG = "workers/web-ui-static/wrangler.jsonc"


def _load_dotenv() -> None:
    env_path = _REPO / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _npx() -> str:
    found = shutil.which("npx") or shutil.which("npx.cmd")
    if not found:
        raise FileNotFoundError("npx not on PATH")
    return found


def _run(argv: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=_REPO,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )


def _emit(text: str) -> None:
    sys.stdout.buffer.write((text or "").encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")


def main() -> int:
    _load_dotenv()
    token_ok = bool(os.environ.get("CLOUDFLARE_API_TOKEN"))
    account_ok = bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    pub = os.environ.get("SUPABASE_PUBLISHABLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or ""
    print("token_set=", token_ok, "account_set=", account_ok, "publishable_set=", bool(pub))
    if not token_ok:
        print("missing CLOUDFLARE_API_TOKEN")
        return 2

    npx = _npx()
    print("npx=", npx)

    dry = _run(
        [
            npx,
            "--yes",
            "wrangler",
            "deploy",
            "--dry-run",
            "--config",
            _CONFIG,
        ]
    )
    print("dry_exit=", dry.returncode)
    _emit(dry.stdout or "")
    _emit(dry.stderr or "")
    if dry.returncode != 0:
        return dry.returncode

    live = _run(
        [
            npx,
            "--yes",
            "wrangler",
            "deploy",
            "--config",
            _CONFIG,
        ]
    )
    print("deploy_exit=", live.returncode)
    _emit(live.stdout or "")
    _emit(live.stderr or "")
    if live.returncode != 0:
        return live.returncode

    if not pub:
        print("skip_secret_put publishable_missing")
        return 0

    secret = _run(
        [
            npx,
            "--yes",
            "wrangler",
            "secret",
            "put",
            "SUPABASE_PUBLISHABLE_KEY",
            "--config",
            _CONFIG,
        ],
        input_text=pub + "\n",
    )
    print("secret_put_exit=", secret.returncode)
    out = (secret.stdout or "") + (secret.stderr or "")
    redacted = out.replace(pub, "[redacted]")
    _emit(redacted)
    return secret.returncode


if __name__ == "__main__":
    raise SystemExit(main())
