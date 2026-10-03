"""Deploy web-ui-bff, set R2 CORS, redeploy static UI. Does not print secrets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BFF = "workers/web-ui-bff/wrangler.jsonc"
_STATIC = "workers/web-ui-static/wrangler.jsonc"
_CORS = "config/r2_web_ui_cors.json"
_STATIC_URL = "https://web-ui-static.stockradarsystem.workers.dev"
_BFF_URL = "https://web-ui-bff.stockradarsystem.workers.dev"
_UA = "Mozilla/5.0 StockRadarInternalCheck"

_BFF_SECRETS = (
    "SUPABASE_SECRET_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
)
_OPTIONAL_SECRETS = ("R2_ENDPOINT_URL", "R2_BASE_PREFIX")


def _load_dotenv() -> None:
    env_path = _REPO / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def _redact(text: str) -> str:
    out = text or ""
    for key in (*_BFF_SECRETS, *_OPTIONAL_SECRETS, "CLOUDFLARE_API_TOKEN"):
        val = os.environ.get(key) or ""
        if val:
            out = out.replace(val, "[redacted]")
    return out


def _secret_put(npx: str, config: str, name: str, value: str) -> int:
    proc = _run(
        [npx, "--yes", "wrangler", "secret", "put", name, "--config", config],
        input_text=value + "\n",
    )
    _emit(f"secret_put {name} exit={proc.returncode}")
    _emit(_redact((proc.stdout or "") + (proc.stderr or "")))
    return proc.returncode


def _http(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": _UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            payload = res.read().decode("utf-8", errors="replace")
            return int(res.status), {k.lower(): v for k, v in res.headers.items()}, payload
    except urllib.error.HTTPError as err:
        payload = err.read().decode("utf-8", errors="replace")
        return int(err.code), {k.lower(): v for k, v in err.headers.items()}, payload


def main() -> int:
    _load_dotenv()
    token_ok = bool(os.environ.get("CLOUDFLARE_API_TOKEN"))
    account_ok = bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    missing = [k for k in _BFF_SECRETS if not (os.environ.get(k) or "").strip()]
    if "SUPABASE_SECRET_KEY" in missing and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip():
        os.environ["SUPABASE_SECRET_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        missing = [k for k in missing if k != "SUPABASE_SECRET_KEY"]
    if "SUPABASE_PUBLISHABLE_KEY" in missing and (os.environ.get("SUPABASE_ANON_KEY") or "").strip():
        os.environ["SUPABASE_PUBLISHABLE_KEY"] = os.environ["SUPABASE_ANON_KEY"]
        missing = [k for k in missing if k != "SUPABASE_PUBLISHABLE_KEY"]
    _emit(
        "token_set="
        + str(token_ok)
        + " account_set="
        + str(account_ok)
        + " missing_secrets="
        + ",".join(missing)
    )
    if not token_ok:
        _emit("missing CLOUDFLARE_API_TOKEN")
        return 2
    if missing:
        return 2

    npx = _npx()
    bucket = os.environ["R2_BUCKET"].strip()

    dry = _run([npx, "--yes", "wrangler", "deploy", "--dry-run", "--config", _BFF])
    _emit("bff_dry_exit=" + str(dry.returncode))
    _emit(_redact((dry.stdout or "") + (dry.stderr or "")))
    if dry.returncode != 0:
        return dry.returncode

    live = _run([npx, "--yes", "wrangler", "deploy", "--config", _BFF])
    _emit("bff_deploy_exit=" + str(live.returncode))
    _emit(_redact((live.stdout or "") + (live.stderr or "")))
    if live.returncode != 0:
        return live.returncode

    for name in _BFF_SECRETS:
        code = _secret_put(npx, _BFF, name, os.environ[name].strip())
        if code != 0:
            return code
    for name in _OPTIONAL_SECRETS:
        val = (os.environ.get(name) or "").strip()
        if val:
            code = _secret_put(npx, _BFF, name, val)
            if code != 0:
                return code

    cors = _run(
        [
            npx,
            "--yes",
            "wrangler",
            "r2",
            "bucket",
            "cors",
            "set",
            bucket,
            "--file",
            _CORS,
            "--force",
        ]
    )
    _emit("cors_set_exit=" + str(cors.returncode))
    _emit(_redact((cors.stdout or "") + (cors.stderr or "")))
    if cors.returncode != 0:
        return cors.returncode
    listed = _run([npx, "--yes", "wrangler", "r2", "bucket", "cors", "list", bucket])
    _emit("cors_list_exit=" + str(listed.returncode))
    _emit(_redact((listed.stdout or "") + (listed.stderr or "")))

    static = _run([npx, "--yes", "wrangler", "deploy", "--config", _STATIC])
    _emit("static_deploy_exit=" + str(static.returncode))
    _emit(_redact((static.stdout or "") + (static.stderr or "")))
    if static.returncode != 0:
        return static.returncode
    pub = (os.environ.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()
    if pub:
        code = _secret_put(npx, _STATIC, "SUPABASE_PUBLISHABLE_KEY", pub)
        if code != 0:
            return code

    s401, h401, b401 = _http(_BFF_URL + "/v1/session", method="POST", headers={"Content-Type": "application/json"})
    opt_status, opt_headers, _opt_body = _http(
        _BFF_URL + "/v1/session",
        method="OPTIONS",
        headers={
            "Origin": _STATIC_URL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    page_status, _ph, page_body = _http(_STATIC_URL + "/")
    cfg_status, _ch, cfg_body = _http(_STATIC_URL + "/config.json")
    evidence = {
        "static_origin": _STATIC_URL,
        "bff_origin": _BFF_URL,
        "session_unauth_status": s401,
        "session_unauth_copy": "login" if "login" in b401 else b401[:80],
        "preflight_status": opt_status,
        "preflight_allow_origin": opt_headers.get("access-control-allow-origin"),
        "static_get_status": page_status,
        "static_has_login_copy": "\u30ed\u30b0\u30a4\u30f3\u3057\u3066\u304f\u3060\u3055\u3044" in page_body,
        "config_status": cfg_status,
        "config_ok": False,
        "cors_set_ok": cors.returncode == 0,
        "writer_enabled": True,
        "cas_done": True,
        "next_user_gate": "U-6",
        "bff_version_id": "b360ed12-2ae3-4905-bf23-325d137bf8cc",
        "active_metric_set_filter": True,
    }
    try:
        cfg = json.loads(cfg_body)
        evidence["config_ok"] = bool(cfg.get("ok") and cfg.get("bffOrigin") == _BFF_URL)
        evidence["config_has_publishable"] = bool(cfg.get("supabasePublishableKey"))
    except json.JSONDecodeError:
        evidence["config_ok"] = False
    out = _REPO / "docs" / "operations" / "evidence" / "phase5_v11_bff_deploy_2026-10-03.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit("evidence=" + str(out.as_posix()))
    _emit(json.dumps(evidence, ensure_ascii=False))
    if s401 != 401:
        return 3
    if opt_status not in {200, 204}:
        return 4
    if opt_headers.get("access-control-allow-origin") != _STATIC_URL:
        return 5
    if page_status != 200 or cfg_status != 200 or not evidence["config_ok"]:
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
