"""Supabase control-plane anon/authenticated denial smoke (Secrets required).

Manual dispatch only (.github/workflows/supabase_security_smoketest.yml).
Does NOT call commit_jpx_url_cache (production jpx-latest-url pointer).

Valid-key positive control uses GET /auth/v1/health because PostgREST root
(/rest/v1/) returns 401 for anon once all public table grants are revoked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

CONTROL_PLANE_TABLES = (
    "runs",
    "artifact_index",
    "cache_index",
    "cache_pointers",
    "monthly_snapshots",
    "publish_status",
)

COMMIT_FIXED_CACHE_SIG = "commit_fixed_cache"
COMMIT_JPX_URL_CACHE_SIG = "commit_jpx_url_cache"

POSTGREST_INSUFFICIENT_PRIVILEGE = "42501"
AUTH_HEALTH_PATH = "/auth/v1/health"

_COMMIT_FIXED_CACHE_BODY = {
    "p_cache_key": "p0-smoke-deny",
    "p_object_key": "p0-smoke-deny",
    "p_sha256": "0" * 64,
    "p_size_bytes": 1,
    "p_writer_workflow": "p0-security-smoke",
    "p_source_github_run_id": 0,
    "p_history_id": "00000000-0000-0000-0000-000000000001",
}
_COMMIT_JPX_URL_CACHE_BODY = {
    "p_object_key": "p0-smoke-deny",
    "p_sha256": "0" * 64,
    "p_size_bytes": 1,
    "p_writer_workflow": "p0-security-smoke",
    "p_source_github_run_id": 0,
    "p_history_id": "00000000-0000-0000-0000-000000000001",
}

_SMOKE_UUID = "00000000-0000-0000-0000-000000000001"
_SMOKE_SHA256 = "0" * 64

_TABLE_WRITE_CONFIG: dict[str, dict[str, Any]] = {
    "runs": {
        "post": {"id": _SMOKE_UUID, "workflow": "p0-security-smoke", "github_run_id": 0},
        "patch": {"status": "failed"},
        "filter_col": "id",
        "filter_val": _SMOKE_UUID,
    },
    "artifact_index": {
        "post": {
            "id": _SMOKE_UUID,
            "run_id": "00000000-0000-0000-0000-000000000002",
            "source_name": "p0-security-smoke",
            "object_key": "p0-smoke-deny",
            "sha256": _SMOKE_SHA256,
        },
        "patch": {"status": "orphan"},
        "filter_col": "id",
        "filter_val": _SMOKE_UUID,
    },
    "cache_index": {
        "post": {
            "cache_key": "p0-security-smoke",
            "cache_kind": "fixed",
            "object_key": "p0-smoke-deny",
            "sha256": _SMOKE_SHA256,
            "writer_workflow": "p0-security-smoke",
            "source_ref": "n/a",
        },
        "patch": {"status": "orphan"},
        "filter_col": "id",
        "filter_val": _SMOKE_UUID,
    },
    "cache_pointers": {
        "post": {
            "cache_key": "p0-security-smoke",
            "object_key": "p0-smoke-deny",
            "sha256": _SMOKE_SHA256,
            "size_bytes": 1,
            "writer_workflow": "p0-security-smoke",
            "source_github_run_id": 0,
        },
        "patch": {"object_key": "p0-smoke-deny-patch"},
        "filter_col": "cache_key",
        "filter_val": "p0-security-smoke",
    },
    "monthly_snapshots": {
        "post": {
            "monthly_tag": "p0-security-smoke",
            "snapshot_date": "2026-01-01",
            "github_run_id": 0,
            "object_keys": {"monthly_snapshots_schema_version": 1},
            "sha256": _SMOKE_SHA256,
        },
        "patch": {"status": "orphan"},
        "filter_col": "monthly_tag",
        "filter_val": "p0-security-smoke",
    },
    "publish_status": {
        "post": {
            "run_id": "00000000-0000-0000-0000-000000000002",
            "github_run_id": 0,
            "run_date": "2026-01-01",
            "logical_kind": "indicators_csv",
            "visibility": "work",
            "object_key": "p0-smoke-deny",
            "manifest_object_key": "p0-smoke-deny-manifest",
            "size_bytes": 1,
            "sha256": _SMOKE_SHA256,
            "content_type": "text/csv",
        },
        "patch": {"status": "orphan"},
        "filter_col": "id",
        "filter_val": _SMOKE_UUID,
    },
}


def _load_dotenv() -> None:
    import os

    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _fail(msg: str) -> int:
    print(f"security smoke failed: {msg}", file=sys.stderr)
    return 1


def _headers(api_key: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _request(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    json_body: Any | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    return client.request(
        method,
        f"{base_url}{path}",
        headers=_headers(api_key),
        json=json_body,
        params=params,
    )


def _parse_postgrest_code(resp: httpx.Response) -> str | None:
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        code = payload.get("code")
        return str(code) if code is not None else None
    return None


def _assert_denied(resp: httpx.Response, *, context: str) -> str | None:
    if resp.status_code not in {401, 403}:
        return f"{context}: expected HTTP 401/403, got {resp.status_code}"
    code = _parse_postgrest_code(resp)
    if code != POSTGREST_INSUFFICIENT_PRIVILEGE:
        return f"{context}: expected PostgREST code {POSTGREST_INSUFFICIENT_PRIVILEGE}, got {code!r}"
    return None


def main() -> int:
    import os

    _load_dotenv()
    base_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    publishable = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not publishable:
        publishable = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not base_url or not publishable:
        return _fail("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) required")

    invalid_key = "invalid-publishable-key-for-p0-smoke"

    with httpx.Client(timeout=30.0) as client:
        invalid_resp = _request(
            client,
            base_url=base_url,
            api_key=invalid_key,
            method="GET",
            path=AUTH_HEALTH_PATH,
        )
        if invalid_resp.status_code != 401:
            return _fail(f"invalid key control: expected HTTP 401, got {invalid_resp.status_code}")

        valid_control = _request(
            client,
            base_url=base_url,
            api_key=publishable,
            method="GET",
            path=AUTH_HEALTH_PATH,
        )
        if valid_control.status_code != 200:
            return _fail(
                f"valid key control: expected HTTP 200 on GET {AUTH_HEALTH_PATH}, "
                f"got {valid_control.status_code}"
            )

        for table in CONTROL_PLANE_TABLES:
            cfg = _TABLE_WRITE_CONFIG[table]
            filter_params = {str(cfg["filter_col"]): f"eq.{cfg['filter_val']}"}
            for method, path, body, params in (
                ("GET", f"/rest/v1/{table}", None, {"limit": "1"}),
                ("POST", f"/rest/v1/{table}", cfg["post"], None),
                ("PATCH", f"/rest/v1/{table}", cfg["patch"], filter_params),
                ("DELETE", f"/rest/v1/{table}", None, filter_params),
            ):
                resp = _request(
                    client,
                    base_url=base_url,
                    api_key=publishable,
                    method=method,
                    path=path,
                    json_body=body if method in {"POST", "PATCH"} else None,
                    params=params,
                )
                err = _assert_denied(resp, context=f"{method} {table}")
                if err:
                    return _fail(err)

        for rpc, body in (
            (COMMIT_FIXED_CACHE_SIG, _COMMIT_FIXED_CACHE_BODY),
            (COMMIT_JPX_URL_CACHE_SIG, _COMMIT_JPX_URL_CACHE_BODY),
        ):
            resp = _request(
                client,
                base_url=base_url,
                api_key=publishable,
                method="POST",
                path=f"/rest/v1/rpc/{rpc}",
                json_body=body,
            )
            err = _assert_denied(resp, context=f"RPC {rpc}")
            if err:
                return _fail(err)

    print("security smoke ok: anon publishable key denied on control-plane tables and RPCs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
