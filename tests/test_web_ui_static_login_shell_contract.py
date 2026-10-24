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
    chrome_js = (_STATIC / "assets" / "chrome.js").read_text(encoding="utf-8")
    chrome_css = (_STATIC / "assets" / "chrome.css").read_text(encoding="utf-8")
    blob = html + "\n" + js + "\n" + live + "\n" + chrome_js + "\n" + chrome_css
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


def test_app_js_escapes_bundle_html() -> None:
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    proto = (_REPO / "prototypes" / "web-ui-asof" / "web" / "app.js").read_text(encoding="utf-8")
    for blob in (app, proto):
        assert "function safeHttpUrl" in blob
        assert "escapeHtml(row.name || \"\")" in blob
        assert "return '<a href=\"' + String(v)" not in blob
        assert "return v == null ? \"\" : escapeHtml(String(v));" in blob
    assert "td.innerHTML = cellHtml" in proto
    assert "cellHtml(row, k)" in app
    assert "tbody.innerHTML" in app.split("function renderTable")[1].split("function yZ")[0]


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
    assert "function isTextFilterCol" in app
    assert "function openTextFilterMenu" in app
    assert 'filt.op === "contains"' in app
    assert "function toHalfWidthCode" in app
    assert "imeMode = \"disabled\"" in app
    assert "el.inputMode = \"url\"" in app
    assert "function bindHalfWidthCodeInput" in app
    assert "schedulePrefsSave();" in app.split("function renderColsPanel")[1].split("function renderLegend")[0]
    assert "requestViewRefresh();" in app.split("function renderColsPanel")[1].split("function renderLegend")[0]
    assert "schedulePrefsSave();" in app.split("function saveTabSettings")[1].split("function openTabSettingsModal")[0]
    assert "function requestViewRefresh" in app
    assert "function stickyColClass" in app
    assert "function scheduleStickyColOffsets" in app
    assert "sticky-col-code" in app
    assert 'selected ? "accent"' in app
    assert "function closeAccountMenu" in app
    assert "function normalizeFavLists" in app
    assert "function openFavFlyout" in app
    assert "const FAV_LIST_MAX = 12" in app
    assert "function syncFavCreateFields" in app
    assert "function favCodeAddAtCap" in app
    assert "最大数に達しています" in app
    assert 'syncFavCreateFields($("fav-list-add-code")' in app
    assert "const FAV_CELL_CHIPS = 5" in app
    assert "filter_ids: state.favFilterIds.slice()" in app
    assert "opts.toggle && next && state.selected === next" in app
    assert 'if (!state.selected) scrollChartCardIntoView(next);' in app
    assert "function sameCodeList" in app
    assert "function makeChartCard" in app
    assert "function bindGridEvents" in app
    assert 'btn.classList.add("th-filter-btn")' in app
    assert 'th.classList.add("th-filterable")' in app
    assert 'const FAV_FILTER_BLANK = "__blank__"' in app
    assert 'createElement("wa-dropdown")' in app
    assert 'item.type = "checkbox"' in app
    assert "function favFilterableLists" in app
    assert "list.codes.length > 0" in app
    assert 'chip.slot = "icon"' in app
    assert ".col-filter-menu, .fav-filter-anchor, .fav-flyout, .account-menu, .th-filter-btn, [data-surface-header], wa-dropdown" in app
    assert 'className = "fav-filter-anchor"' in app
    assert "numberCellFormat" in app
    legend_fn = app.split("function renderLegend")[1].split("function stickyColClass")[0]
    assert "ui.tag" in legend_fn
    assert 'createElement("span")' in legend_fn
    assert "seriesDisplayMeta()" in legend_fn
    hover_table = app.split("function fillChartHoverTable")[1].split("function setChartHoverIndex")[0]
    assert "seriesDisplayMeta()" in hover_table
    display_fn = app.split("function seriesDisplayMeta")[1].split("const state")[0]
    assert "z_disp" in display_fn
    assert "rs.reverse()" in display_fn
    assert "host.innerHTML = \"\"" not in app.split("function refreshCharts")[1].split("const TAB_SETTINGS_DEFAULT")[0]


@pytest.mark.unit
def test_web_ui_static_boot_progress_hides_login_until_session() -> None:
    html = _HTML.read_text(encoding="utf-8")
    live = (_STATIC / "assets" / "live.js").read_text(encoding="utf-8")
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    css = (_STATIC / "assets" / "styles.css").read_text(encoding="utf-8")
    assert 'id="login-shell" hidden' in html
    assert 'id="app-root" hidden' in html
    assert 'id="boot-progress"' in html
    assert 'id="boot-progress-bar"' in html
    assert 'id="view-busy"' in html
    assert 'id="account-toggle"' in html
    assert 'id="account-dropdown"' in html
    assert "<wa-dropdown" in html
    assert "<wa-dropdown-item" in html
    assert 'id="account-logout"' in html
    assert 'id="account-fav-lists"' in html
    assert 'id="account-menu-panel"' not in html
    assert "function toggleAccountMenu" not in app
    assert "function confirmDestructive" in app
    assert 'id="confirm-dialog"' in html
    assert "<wa-dialog" in html
    assert 'id="fav-lists-modal"' in html
    assert 'id="fav-list-rename"' in html
    assert 'id="fav-list-delete"' in html
    assert "fav-list-drag" in app
    assert "function reorderFavLists" in app
    assert 'window.prompt("リスト名"' not in app
    assert "fav-flyout" in css
    assert ".chart-hover-table" in css
    assert ".chart-hover-head" in css
    assert ".chart-hover-cell" in css
    table_css = css.split(".chart-hover-table")[1].split(".chart-hover-date")[0].replace(" ", "")
    assert "minmax(0,1fr)" in table_css
    assert "width:100%" in table_css
    assert "font-size:11px" in css.split(".chart-card .hover")[1].split(".kabutan")[0]
    assert ".fav-chip" in css
    assert "width:12px; height:12px" in css.split(".fav-chip")[1].split(".fav-more")[0]
    assert "width:12px; height:12px" in css.split(".fav-empty")[1].split(".fav-flyout")[0]
    assert "flex-wrap:wrap" in css.split("button.fav-star.on")[1].split("button.fav-star.disabled")[0]
    assert "justify-content:center" in css.split("button.fav-star.on")[1].split("button.fav-star.disabled")[0]
    assert 'class="fav-empty"' in app
    assert "☆" not in app.split("function favCellInnerHtml")[1].split("function closeFavFlyout")[0]
    assert "1px dashed" in css.split(".fav-empty")[1].split(".fav-flyout")[0]
    assert "sticky-col-name" in css
    assert "border-collapse:separate" in css.replace(" ", "")
    assert "nth-child(even) td.sticky-col" not in css
    assert "#login-shell" in css
    assert "max-width: 28rem" in css
    assert "view-busy-slide" in css
    assert "signOut" in live
    assert "window.__webUiLogout" in live
    assert "function requestViewRefresh" in app
    assert "読み込み中" in html
    assert "#boot-progress[hidden]" in html
    bar_css = css.split("#boot-progress-bar")[1].split("}")[0]
    assert "width:100%" in bar_css.replace(" ", "")
    assert "width:8%" not in bar_css.replace(" ", "")
    assert "function revealLoginForm" in live
    assert "window.__webUiProgress" in live
    assert "bindLoginForm" in live
    boot_fn = live.split("async function boot()")[1]
    assert "getSession" in boot_fn
    assert boot_fn.index("getSession") < boot_fn.index("revealLoginForm()")
    assert "if (session)" in boot_fn
    assert boot_fn.index("if (session)") < boot_fn.index("revealLoginForm()")
    assert "function bootProgress" in app
    assert "function readBodyWithProgress" in app
    assert "content-length" in app
    assert "signed_url" not in html
    assert "object_key" not in html


@pytest.mark.unit
def test_web_ui_static_bundles_webawesome_only() -> None:
    package = json.loads((_STATIC / "package.json").read_text(encoding="utf-8"))
    html = _HTML.read_text(encoding="utf-8")
    chrome_js = (_STATIC / "assets" / "chrome.js").read_text(encoding="utf-8")
    chrome_css = (_STATIC / "assets" / "chrome.css").read_text(encoding="utf-8")
    ui_chrome = (_STATIC / "ui" / "chrome.js").read_text(encoding="utf-8")
    theme = (_STATIC / "ui" / "theme.css").read_text(encoding="utf-8")
    formatter = (_STATIC / "ui" / "conditional-format.js").read_text(encoding="utf-8")
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    vite = (_STATIC / "vite.config.js").read_text(encoding="utf-8")
    blob = html + "\n" + chrome_js + "\n" + chrome_css + "\n" + ui_chrome

    assert package["dependencies"] == {"@awesome.me/webawesome": "3.14.0"}
    assert package["devDependencies"] == {"vite": "8.3.2"}
    assert 'outDir: "assets"' in vite
    assert "emptyOutDir: false" in vite
    assert 'href="/chrome.css"' in html
    assert 'src="/chrome.js"' in html
    assert 'class="wa-dark"' in html
    assert "<wa-card" in html
    assert "<wa-input" in html
    assert "<wa-button" in html
    assert "<wa-select" in html
    assert "<wa-dropdown" in html
    assert "<wa-dialog" in html
    assert "<wa-tab-group" in html
    assert "dialog/dialog.js" in ui_chrome
    assert "StockRadarChrome" in chrome_js
    assert "wa-button" in chrome_js
    assert "Yu Gothic UI" in theme
    assert "color-mix(in oklab, var(--wa-color-gray-05), black 20%)" in theme
    assert "--surface-raised: #0d1924" in theme
    assert 'const POSITIVE_HUE = "156 58% 48%"' in formatter
    assert 'const NEGATIVE_HUE = "346 72% 58%"' in formatter
    assert "0.08 + intensity * 0.2" in formatter
    assert "MutationObserver" not in formatter
    assert "MutationObserver" not in ui_chrome
    assert "export function numberCellFormat" in formatter
    assert "export function cfRangeForLabel" in formatter
    assert "export function priceTone" in formatter
    assert "numberCellFormat" in ui_chrome
    assert "cfRangeForLabel" in ui_chrome
    assert "priceTone" in ui_chrome
    assert "applyConditionalFormatting" in ui_chrome
    td_markup = app.split("function tdMarkup")[1].split("function bindGridEvents")[0]
    assert "numberCellFormat" in td_markup
    assert "cfRangeForLabel" in td_markup
    assert "priceTone" in td_markup
    hover_fn = app.split("function drawChartHoverMarker")[1].split("function asOfQuery")[0]
    assert "chart-hover-table" in hover_fn
    assert "chart-hover-head" in hover_fn
    assert "numberCellFormat" in hover_fn
    assert "cfRangeForLabel" in hover_fn
    assert "surface-cf-number" in hover_fn
    assert "innerHTML" in hover_fn
    assert "disp=" not in hover_fn
    assert "function latestChartIndex" in hover_fn
    assert "pointerleave" in hover_fn
    assert ".length - 1" in hover_fn
    assert 'textContent = parts.join(" | ")' not in hover_fn
    assert "cellStyle(" not in td_markup
    render_table = app.split("function renderTable")[1].split("function yZ")[0]
    assert "cellStyle(" not in render_table
    assert "tbody.innerHTML" in render_table
    assert "sameCodeList" in render_table
    assert "requestViewRefresh" in app
    assert 'id="view-busy"' in html
    assert "surface-cf-number" in chrome_css
    assert ".chart-hover-cell.surface-cf-number" in theme
    assert "hsl(var(--cell-hue)/var(--cell-alpha))" in chrome_css.replace(" ", "")
    assert ".chart-card [data-chart-title]" in chrome_css
    assert "font-weight:400" in chrome_css.replace(" ", "")
    assert ".chart-card wa-card::part(header)" in theme
    assert ".chart-card wa-card::part(body)" in theme
    assert "padding: 12px" in theme.split(".chart-card wa-card::part(header)")[1].split("}")[0]
    assert "border-radius: 12px" in theme.split(".chart-card wa-card {")[1].split("}")[0]
    render_table = app.split("function renderTable")[1].split("function yZ")[0]
    assert "CF_LO" not in render_table
    assert "PRICE_TEXT_CF" not in render_table
    for forbidden in (
        "spectrum-web-components",
        "@ui5/",
        "@vaadin/",
        "@lion/",
        "library-switcher",
        "cdn.jsdelivr",
        "unpkg.com",
        "jsdelivr.net",
        "surface-preview-boot",
    ):
        assert forbidden not in blob
    for token in _FORBIDDEN:
        assert token.lower() not in chrome_js.lower()
        assert token.lower() not in chrome_css.lower()


@pytest.mark.unit
def test_app_js_composes_price_text_from_candle_labels() -> None:
    html = _HTML.read_text(encoding="utf-8")
    app = (_STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    dictionary = (_STATIC / "assets" / "price-text.js").read_text(encoding="utf-8")
    assert '<script src="/price-text.js"></script>' in html
    assert "function displayPriceText" in app
    assert "displayPriceText(row)" in app
    assert "row.price_text" not in app.split("function cellStyle")[1].split("function mapKey")[0]
    assert "function priceTextAvailable" in app
    assert "function orderVisibleKeys" in app
    assert 'state.allKeys.includes("candle_labels")' in app
    assert "window.StockRadarPriceText" in dictionary
    assert '["GAP_UP", "\u4e0a\u7a93\uff0b"]' in dictionary
    assert '["GAP_DOWN", "\u4e0b\u7a93\uff0b"]' in dictionary
    assert "function fromLabels" in dictionary
    assert "function hasCandleLabels" in dictionary
    assert "if (hasCandleLabels(row)) return fromLabels(row.candle_labels);" in dictionary
    assert "row.candle_labels" in dictionary
    display_fn = app.split("function displayPriceText")[1].split("function cellStyle")[0]
    assert "api.displayText" in display_fn
    assert "row.candle_labels" in display_fn

