"""Login-shell Worker: workers_dev true, T-5 copy, no secrets in assets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_STATIC = _REPO / "workers" / "web-ui-static"
_DISPATCHER = _REPO / "workers" / "github-cron-dispatcher" / "wrangler.toml"
_WRANGLER = _STATIC / "wrangler.jsonc"
_HTML = _STATIC / "assets" / "index.html"
_JS = _STATIC / "src" / "index.js"
_README = _STATIC / "README.md"

_FORBIDDEN = (
    "service_role",
    "SUPABASE_SECRET",
    "SECRET_KEY",
    "signed_url",
    "object_key",
    "eyJ",  # JWT fragment / service key prefix
)


@pytest.mark.unit
def test_web_ui_static_workers_dev_true_and_isolated() -> None:
    cfg = json.loads(_WRANGLER.read_text(encoding="utf-8"))
    assert cfg["name"] == "web-ui-static"
    assert cfg["workers_dev"] is True
    assert cfg["assets"]["directory"] == "./assets"
    assert cfg["assets"]["binding"] == "ASSETS"
    assert cfg["vars"]["LOGIN_SHELL"] == "0"
    assert "https://wocvepixlzqupasoipbk.supabase.co" in cfg["vars"]["SUPABASE_URL"]
    dispatcher = _DISPATCHER.read_text(encoding="utf-8")
    assert "workers_dev = false" in dispatcher
    assert "github-cron-dispatcher" in dispatcher
    readme = _README.read_text(encoding="utf-8")
    assert "npx wrangler deploy --config workers/web-ui-static/wrangler.jsonc" in readme
    assert "workers_dev" in readme


@pytest.mark.unit
def test_web_ui_static_login_shell_t5_copy_no_secrets() -> None:
    html = _HTML.read_text(encoding="utf-8")
    js = _JS.read_text(encoding="utf-8")
    live = (_STATIC / "assets" / "live.js").read_text(encoding="utf-8")
    blob = html + "\n" + js + "\n" + live
    assert "\u30ed\u30b0\u30a4\u30f3\u3057\u3066\u304f\u3060\u3055\u3044" in html
    assert "\u5229\u7528\u3067\u304d\u307e\u305b\u3093" in html
    assert "\u4e00\u6642\u7684\u306b\u5229\u7528\u3067\u304d\u307e\u305b\u3093" in html
    assert "signInWithOtp" in live
    assert "createClient" in live
    assert "/config.json" in live
    assert "emailRedirectTo" in live
    assert "not_found_handling" in _WRANGLER.read_text(encoding="utf-8")
    for token in _FORBIDDEN:
        assert token.lower() not in blob.lower()
    assert "SUPABASE_PUBLISHABLE_KEY" not in html
    assert "GetObject" not in html
    assert "signed_url" not in html


@pytest.mark.unit
def test_web_ui_static_worker_does_not_mint() -> None:
    js = _JS.read_text(encoding="utf-8")
    assert "ASSETS.fetch" in js
    assert "/config.json" in js
    assert "mint(" not in js.lower()
    assert "R2" not in js
    assert "signed" not in js.lower()


def test_app_js_reads_event_news_bundle() -> None:
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    assert "function eventNewsItems" in app
    assert "row.event_news_bundle" in app
    assert 'state.allKeys.includes("event_news_bundle")' in app


def test_app_js_accel_cf_pm1_and_extra_last_bar() -> None:
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    pm5, _, rest = app.partition("const CF_PM5")
    pm1_src, _, pm1_rest = rest.partition("const CF_PM1")
    assert "rs_acceleration_topix" not in pm1_src.split("];")[0]
    assert "rs_acceleration_topix" in pm1_rest.split("];")[0]
    assert "turnover_ma_ratio_60" in app
    assert "perfect_order_days" in app
    assert "beta_adjusted_rs" in app
    assert "information_ratio" in app
    assert "function reconcileVisibleKeys" in app
    assert "defaultKeysSnapshot" in app
    assert "colFilters: state.colFilters" in app
    assert "schedulePrefsSave();" in app.split("function renderColsPanel")[1].split("function renderLegend")[0]
    assert "schedulePrefsSave();" in app.split("function saveTabSettings")[1].split("function openTabSettingsModal")[0]
