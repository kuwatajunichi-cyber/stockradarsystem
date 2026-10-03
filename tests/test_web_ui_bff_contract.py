"""BFF Worker contract: workers_dev, CORS origin, T-5, no secrets in source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_BFF = _REPO / "workers" / "web-ui-bff"
_STATIC = _REPO / "workers" / "web-ui-static"
_DISPATCHER = _REPO / "workers" / "github-cron-dispatcher" / "wrangler.toml"
_CORS = _REPO / "config" / "r2_web_ui_cors.json"
_FORBIDDEN = (
    "eyJhbG",
    "sk_live",
    "sb_secret_",
    "CLOUDFLARE_API_TOKEN",
)


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert b"\x00" not in raw, f"{path} must be UTF-8 without NUL"
    return raw.decode("utf-8")


def test_bff_workers_dev_true_isolated_from_dispatcher() -> None:
    cfg = json.loads(_read(_BFF / "wrangler.jsonc"))
    assert cfg["name"] == "web-ui-bff"
    assert cfg["workers_dev"] is True
    assert cfg["vars"]["R2_PUBLIC_BUCKET"] == "false"
    assert cfg["vars"]["STATIC_ORIGIN"] == (
        "https://web-ui-static.stockradarsystem.workers.dev"
    )
    dispatcher = _read(_DISPATCHER)
    assert "workers_dev = false" in dispatcher
    assert "github-cron-dispatcher" in dispatcher


def test_bff_source_has_t5_and_no_secrets() -> None:
    blob = "\n".join(
        _read(p)
        for p in (
            _BFF / "src" / "index.js",
            _BFF / "src" / "cors.js",
            _BFF / "src" / "mint.js",
            _BFF / "src" / "jwt.js",
            _BFF / "src" / "r2.js",
        )
    )
    assert "COPY_UNAVAILABLE" in blob
    assert "COPY_TEMPORARY" in blob
    assert "\\u5229\\u7528\\u3067\\u304d\\u307e\\u305b\\u3093" in blob
    assert "\\u4e00\\u6642\\u7684\\u306b\\u5229\\u7528\\u3067\\u304d\\u307e\\u305b\\u3093" in blob
    assert "/v1/session" in blob
    assert "/v1/dates" in blob
    assert "/v1/mint" in blob
    assert "active_metric_set" in blob
    assert "metric_set_version_id=eq." in blob
    assert "/v1/preferences" in blob
    assert "Authorization" in blob
    assert "derived-web-asof/" in blob
    for token in _FORBIDDEN:
        assert token.lower() not in blob.lower()
    assert "SUPABASE_SECRET_KEY" in blob
    assert "env.R2_SECRET_ACCESS_KEY" in blob


def test_r2_cors_get_head_static_origin_only() -> None:
    cfg = json.loads(_read(_CORS))
    rules = cfg["rules"]
    assert len(rules) == 1
    allowed = rules[0]["allowed"]
    assert allowed["origins"] == [
        "https://web-ui-static.stockradarsystem.workers.dev"
    ]
    methods = {m.upper() for m in allowed["methods"]}
    assert methods == {"GET", "HEAD"}
    blob = _read(_CORS).upper()
    assert "PUT" not in blob
    assert "DELETE" not in blob
    assert "POST" not in blob


def test_static_config_exposes_bff_origin() -> None:
    cfg = json.loads(_read(_STATIC / "wrangler.jsonc"))
    assert cfg["workers_dev"] is True
    assert cfg["vars"]["LOGIN_SHELL"] == "0"
    assert cfg["vars"]["BFF_ORIGIN"] == (
        "https://web-ui-bff.stockradarsystem.workers.dev"
    )
    js = _read(_STATIC / "src" / "index.js")
    assert "bffOrigin" in js
    html = _read(_STATIC / "assets" / "index.html")
    assert "\u30ed\u30b0\u30a4\u30f3\u3057\u3066\u304f\u3060\u3055\u3044" in html
    assert "\u5229\u7528\u3067\u304d\u307e\u305b\u3093" in html
    assert "\u4e00\u6642\u7684\u306b\u5229\u7528\u3067\u304d\u307e\u305b\u3093" in html
    assert "signed_url" not in html
    assert "object_key" not in html
    app = _read(_STATIC / "assets" / "app.js")
    assert "DecompressionStream" in app
    assert "Authorization" in app
    assert "signed_url" in app
    assert "textContent = minted" not in app
    live = _read(_STATIC / "assets" / "live.js")
    assert "signInWithOtp" in live
    assert "/v1/session" in live
