"""Production-parity contracts for the Web Awesome surface prototype."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[1]
_PROTOTYPE = _REPO / "prototypes" / "web-ui-webawesome"
_PRODUCTION = _REPO / "workers" / "web-ui-static" / "assets"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _expected_prototype_html() -> str:
    production = _text(_PRODUCTION / "index.html")
    production = production.replace(
        '<link rel="stylesheet" href="/styles.css" />',
        '<script type="module" src="/src/theme.js"></script>',
    )
    production = production.replace(
        '  <script src="/price-text.js"></script>\n'
        '  <script src="/app.js"></script>\n'
        '  <script type="module" src="/live.js"></script>',
        '  <script src="/price-text.js"></script>\n'
        '  <script src="/production-app.js"></script>\n'
        '  <script type="module" src="/src/mock-live.js"></script>',
    )
    return (
        "<!-- Generated from workers/web-ui-static/assets/index.html. "
        "Do not hand-edit. -->\n"
        + production
    )


@pytest.mark.unit
def test_webawesome_prototype_is_pinned_and_buildable() -> None:
    package = json.loads(_text(_PROTOTYPE / "package.json"))

    assert package["private"] is True
    assert package["dependencies"] == {
        "@awesome.me/webawesome": "3.14.0",
        "@lion/ui": "0.21.1",
        "@spectrum-web-components/action-button": "1.11.2",
        "@spectrum-web-components/button": "1.11.2",
        "@spectrum-web-components/card": "1.11.2",
        "@spectrum-web-components/checkbox": "1.11.2",
        "@spectrum-web-components/divider": "1.11.2",
        "@spectrum-web-components/menu": "1.11.2",
        "@spectrum-web-components/picker": "1.11.2",
        "@spectrum-web-components/progress-bar": "1.11.2",
        "@spectrum-web-components/table": "1.11.2",
        "@spectrum-web-components/tabs": "1.11.2",
        "@spectrum-web-components/textfield": "1.11.2",
        "@spectrum-web-components/theme": "1.11.2",
        "@ui5/webcomponents": "2.26.0",
        "@vaadin/button": "24.4.0",
        "@vaadin/checkbox": "24.4.0",
        "@vaadin/email-field": "24.4.0",
        "@vaadin/horizontal-layout": "24.4.0",
        "@vaadin/progress-bar": "24.4.0",
        "@vaadin/select": "24.4.0",
        "@vaadin/tabs": "24.4.0",
        "@vaadin/text-field": "24.4.0",
        "@vaadin/vaadin-lumo-styles": "24.4.0",
    }
    assert package["devDependencies"]["vite"] == "8.3.2"
    assert package["scripts"]["sync"] == "node scripts/sync-production.mjs"
    assert package["scripts"]["dev"] == "npm run sync && vite --host 127.0.0.1"
    assert package["scripts"]["build"] == "npm run sync && vite build"


@pytest.mark.unit
def test_prototype_is_evaluation_record_not_production_sync_target() -> None:
    html = _text(_PROTOTYPE / "index.html")
    production = _text(_PRODUCTION / "index.html")

    assert "<!-- Generated from workers/web-ui-static/assets/index.html." in html
    assert "/src/theme.js" in html
    assert "/production-app.js" in html
    assert "/price-text.js" in html
    assert "/src/mock-live.js" in html
    assert "library-switcher" not in production
    assert "/chrome.js" in production
    assert "/chrome.css" in production
    assert html == _expected_prototype_html()


@pytest.mark.unit
def test_prototype_keeps_local_evaluation_copies() -> None:
    assert (_PROTOTYPE / "public" / "production-app.js").is_file()
    assert (_PROTOTYPE / "public" / "price-text.js").is_file()
    assert (_PROTOTYPE / "src" / "production.css").is_file()
    assert (_PROTOTYPE / "public" / "production-app.js").read_bytes() == (
        _PRODUCTION / "app.js"
    ).read_bytes()
    assert (_PROTOTYPE / "public" / "price-text.js").read_bytes() == (
        _PRODUCTION / "price-text.js"
    ).read_bytes()
    assert (_PROTOTYPE / "src" / "production.css").read_bytes() == (
        _PRODUCTION / "styles.css"
    ).read_bytes()


@pytest.mark.unit
def test_sync_script_is_fail_fast_and_copies_production_assets() -> None:
    sync = _text(_PROTOTYPE / "scripts" / "sync-production.mjs")

    assert 'copyFileSync(productionAppPath, generatedAppPath)' in sync
    assert 'copyFileSync(productionPriceTextPath, generatedPriceTextPath)' in sync
    assert 'copyFileSync(productionCssPath, generatedCssPath)' in sync
    assert "if (!html.includes(stylesheetTag))" in sync
    assert "if (!html.includes(productionScripts))" in sync


@pytest.mark.unit
def test_local_adapter_only_fakes_io_and_bootstraps_production_app() -> None:
    adapter = _text(_PROTOTYPE / "src" / "mock-live.js")

    for route in ("/v1/dates", "/v1/preferences", "/v1/mint", "/mock/bundle"):
        assert route in adapter
    assert "window.__WEB_UI_CTX" in adapter
    assert "await window.__webUiBoot()" in adapter
    assert 'import "./theme.js"' in adapter
    assert "nativeFetch(input, init)" in adapter
    for forbidden_ui_implementation in (
        "renderTable",
        "renderCharts",
        "drawChart",
        "SERIES_META",
        "innerHTML =",
        "createElement(",
    ):
        assert forbidden_ui_implementation not in adapter


@pytest.mark.unit
def test_local_adapter_does_not_connect_to_production_services() -> None:
    adapter = _text(_PROTOTYPE / "src" / "mock-live.js")

    assert "workers.dev" not in adapter
    assert "supabase.co" not in adapter
    assert "r2.cloudflarestorage.com" not in adapter
    assert "https://esm.sh" not in adapter
    assert 'bffOrigin: window.location.origin' in adapter


@pytest.mark.unit
def test_surface_theme_does_not_hide_or_reimplement_production_ui() -> None:
    theme = _text(_PROTOTYPE / "src" / "theme.js")
    surface = _text(_PROTOTYPE / "src" / "surface.css")
    webawesome = _text(_PROTOTYPE / "src" / "surfaces" / "webawesome.js")
    shared = _text(_PROTOTYPE / "src" / "surface-shared.css")
    switcher = _text(_PROTOTYPE / "src" / "library-switcher.js")

    assert '"./production.css"' in theme
    assert '"./surface-shared.css"' in theme
    assert '"./conditional-format.js"' in theme
    assert '"./library-switcher.js"' in theme
    assert theme.index('"./production.css"') < theme.index('"./surface-shared.css"')
    assert '"../surface.css"' in webawesome
    assert '"../tabs-ui.js"' in webawesome
    assert "--wa-color-brand-60" in surface
    assert "--chart-bg: rgb(9, 7, 32)" in shared
    assert 'select.id = "library-switcher"' in switcher
    for library_id in ("spectrum", "ui5", "vaadin", "lion"):
        assert f"/{library_id}/" in switcher
    css_files = [
        _PROTOTYPE / "src" / "surface.css",
        _PROTOTYPE / "src" / "surface-shared.css",
        *sorted((_PROTOTYPE / "src" / "surfaces").glob("*.css")),
    ]
    for css_path in css_files:
        css = _text(css_path)
        for forbidden in (
            "visibility: hidden",
            "#chart-host canvas",
            ".chart-card canvas",
            "#grid { display: none",
            "#chart-host { display: none",
        ):
            assert forbidden not in css, css_path.name


@pytest.mark.unit
def test_conditional_format_restores_prior_surface_formula_only() -> None:
    formatter = _text(_PROTOTYPE / "src" / "conditional-format.js")
    surface = _text(_PROTOTYPE / "src" / "surface.css")

    assert 'const POSITIVE_HUE = "156 58% 48%"' in formatter
    assert 'const NEGATIVE_HUE = "346 72% 58%"' in formatter
    assert "0.08 + intensity * 0.2" in formatter
    assert 'new MutationObserver(applyConditionalFormatting)' in formatter
    assert 'observer.observe(grid, { childList: true, subtree: true })' in formatter
    assert "surface-cf-number" in surface
    assert "hsl(var(--cell-hue) / var(--cell-alpha))" in surface
    for forbidden_behavior in (
        "window.fetch",
        "__webUiBoot",
        "addEventListener(\"click\"",
        "renderTable",
        "drawChart",
    ):
        assert forbidden_behavior not in formatter


@pytest.mark.unit
def test_table_rows_fit_three_news_lines_and_price_text_uses_real_grammar() -> None:
    adapter = _text(_PROTOTYPE / "src" / "mock-live.js")
    surface = _text(_PROTOTYPE / "src" / "surface.css")
    formatter = _text(_PROTOTYPE / "src" / "conditional-format.js")

    assert "#grid tbody tr,\n#grid tbody td {\n  height: 59px;" in surface
    assert '["防衛関連の大型案件報道", "受注残の更新", "海外事業の進捗観測"]' in adapter
    assert "`event_news_${position}_url`" in adapter
    assert "candle_labels: candleLabels" in adapter
    assert 'price_text: "BUNDLE_PRICE_TEXT_UNUSED"' in adapter
    for labels in (
        "RANGE_LARGE,BODY_MARUBOZU_LIKE,DIR_BULL",
        "GAP_UP,RANGE_VERY_LARGE,WICK_UPPER_LONG,BODY_LONG,DIR_BULL",
        "RANGE_SMALL,WICK_BOTH_PRESENT,DOJI",
        "GAP_DOWN,RANGE_VERY_LARGE,BODY_LONG,DIR_BEAR",
    ):
        assert labels in adapter
    for leftover_server_copy in (
        "上窓＋<極大>長上ヒゲ長陽線",
        "下窓＋<極大>長陰線",
        "<大>丸坊主陽線",
    ):
        assert leftover_server_copy not in adapter
    for invalid_fixture_text in ("高値圏・陽線", "出来高増・陽線", "窓開け上昇", "急反落・陰線"):
        assert invalid_fixture_text not in adapter
    assert "/(陽線|S高)/" in formatter
    assert "/(陰線|S安)/" in formatter


@pytest.mark.unit
def test_webawesome_tabs_wrap_production_tab_behavior() -> None:
    tabs = _text(_PROTOTYPE / "src" / "tabs-ui.js")
    surface = _text(_PROTOTYPE / "src" / "surface.css")

    assert '@awesome.me/webawesome/dist/components/tab-group/tab-group.js' in tabs
    assert 'document.createElement("wa-tab-group")' in tabs
    assert 'document.createElement("wa-tab")' in tabs
    assert 'document.createElement("wa-tab-panel")' in tabs
    assert 'group.addEventListener("wa-tab-show"' in tabs
    assert "sourceButton.click()" in tabs
    assert 'source.style.display = "none"' in tabs
    assert "#surface-kabutan-tab-group wa-tab[active]::part(tab)" in surface
    for forbidden_reimplementation in ("applyKabutanUrl", "kabutanUrl", "renderKabutanTabBar"):
        assert forbidden_reimplementation not in tabs


@pytest.mark.unit
def test_comparison_pages_use_real_library_tabs() -> None:
    theme = _text(_PROTOTYPE / "src" / "theme.js")
    spectrum = _text(_PROTOTYPE / "src" / "surfaces" / "spectrum.js")
    ui5 = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.js")
    vaadin = _text(_PROTOTYPE / "src" / "surfaces" / "vaadin.js")
    lion = _text(_PROTOTYPE / "src" / "surfaces" / "lion.js")

    for library_id in ("webawesome", "spectrum", "ui5", "vaadin", "lion"):
        expected = library_id + ': () => import("./surfaces/' + library_id + '.js")'
        assert expected in theme
    assert 'document.createElement("sp-tabs")' in spectrum
    assert 'document.createElement("sp-tab")' in spectrum
    assert 'setTheme("sap_horizon_dark")' in ui5
    assert 'document.createElement("ui5-tabcontainer")' in ui5
    assert 'document.createElement("vaadin-tabs")' in vaadin
    assert 'document.createElement("lion-tabs")' in lion
    for page in (spectrum, ui5, vaadin, lion):
        assert "installTabHost" in page
        assert "installHeaderHost" in page
        assert "installChromeHost" in page
        for forbidden in ("renderTable", "drawChart", "kabutanUrl"):
            assert forbidden not in page


@pytest.mark.unit
def test_library_headers_wrap_production_thead() -> None:
    host = _text(_PROTOTYPE / "src" / "header-host.js")
    webawesome = _text(_PROTOTYPE / "src" / "surfaces" / "webawesome.js")
    spectrum = _text(_PROTOTYPE / "src" / "surfaces" / "spectrum.js")
    ui5 = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.js")
    vaadin = _text(_PROTOTYPE / "src" / "surfaces" / "vaadin.js")
    lion = _text(_PROTOTYPE / "src" / "surfaces" / "lion.js")
    shared = _text(_PROTOTYPE / "src" / "surface-shared.css")

    assert "installHeaderHost" in host
    assert ".th-filter-btn" in host
    assert "surface-header-source" in host
    assert 'querySelector(".th-filter-btn")?.click()' in host
    assert "filterable" in host
    assert "meta.filterable || meta.numeric" in webawesome
    assert 'document.createElement("wa-button")' in webawesome
    assert 'document.createElement("sp-table-head-cell")' in spectrum
    assert 'document.createElement("ui5-table-header-cell")' in ui5
    assert 'document.createElement("vaadin-button")' in vaadin
    assert 'document.createElement("lion-button")' in lion
    assert ".surface-header-source" in shared
    assert "clip-path: inset(50%)" in shared
    for forbidden in ("renderTable", "drawChart", "openFilterMenu", "kabutanUrl"):
        assert forbidden not in host
        assert forbidden not in webawesome


@pytest.mark.unit
def test_library_chrome_wraps_production_controls() -> None:
    host = _text(_PROTOTYPE / "src" / "chrome-host.js")
    switcher = _text(_PROTOTYPE / "src" / "library-switcher.js")
    shared = _text(_PROTOTYPE / "src" / "surface-shared.css")
    webawesome = _text(_PROTOTYPE / "src" / "surfaces" / "webawesome.js")
    spectrum = _text(_PROTOTYPE / "src" / "surfaces" / "spectrum.js")
    ui5 = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.js")
    vaadin = _text(_PROTOTYPE / "src" / "surfaces" / "vaadin.js")
    lion = _text(_PROTOTYPE / "src" / "surfaces" / "lion.js")

    assert "installChromeHost" in host
    assert "boot-progress" in host
    assert "login-shell" in host
    assert "kabutan-split" in host
    assert "col-filter-menu" in host
    assert "kabutan-blank" in host
    assert "kabutan-blocked-open" in host
    assert "wrapChromeControls" in host
    assert "a#kabutan-blank" in host
    assert ".kabutan-open-tab" in shared
    assert "loginFormHost" in host
    assert "host.append(form)" in host
    assert 'document.createElement("wa-callout")' not in webawesome
    assert 'document.createElement("wa-card")' in webawesome
    assert 'opts.compact === false ? "m" : "xs"' in webawesome
    assert 'document.createElement("wa-select")' in webawesome
    assert 'el.size = "xs"' in webawesome
    assert 'el.size = "s"' not in webawesome
    assert 'opts.strong ? "accent" : "filled-outlined"' in webawesome
    assert 'opts.strong ? "accent" : "plain"' not in webawesome
    assert 'document.createElement("sp-picker")' in spectrum
    assert 'document.createElement("sp-progress-bar")' in spectrum
    assert "document.body.append(theme)" in spectrum
    assert 'document.createElement("sp-button")' in spectrum
    assert 'opts.strong ? "fill" : "outline"' in spectrum
    assert 'el.quiet = !opts.strong' not in spectrum
    assert 'document.createElement("ui5-select")' in ui5
    assert 'document.createElement("ui5-card")' in ui5
    assert 'document.createElement("ui5-progress-indicator")' in ui5
    assert 'opts.strong ? "Emphasized" : "Default"' in ui5
    assert 'opts.strong ? "Emphasized" : "Transparent"' not in ui5
    assert 'document.createElement("vaadin-select")' in vaadin
    assert 'document.createElement("vaadin-progress-bar")' in vaadin
    assert 'opts.strong ? "primary" : ""' in vaadin
    assert '"tertiary small"' not in vaadin
    assert 'document.createElement("lion-select")' in lion
    assert "lion-input-email" in lion
    assert 'id = "surface-preview-boot"' in switcher
    assert 'id = "surface-preview-login"' in switcher
    assert "keepPreview" not in switcher
    assert "起動オーバーレイの確認" not in switcher
    assert "isLibraryInnerControl" in host
    assert "#surface-kabutan-tab-group" in host
    assert '"#boot-progress"' not in host.split("const CHROME_ROOTS", 1)[1].split("const SKIP_CLOSEST", 1)[0]
    for forbidden in ("renderTable", "drawChart", "openFilterMenu", "kabutanUrl"):
        assert forbidden not in host


@pytest.mark.unit
def test_library_chart_pane_wraps_legend_and_card_chrome() -> None:
    host = _text(_PROTOTYPE / "src" / "chart-pane-host.js")
    shared = _text(_PROTOTYPE / "src" / "surface-shared.css")
    webawesome = _text(_PROTOTYPE / "src" / "surfaces" / "webawesome.js")
    spectrum = _text(_PROTOTYPE / "src" / "surfaces" / "spectrum.js")
    ui5 = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.js")
    vaadin = _text(_PROTOTYPE / "src" / "surfaces" / "vaadin.js")
    lion = _text(_PROTOTYPE / "src" / "surfaces" / "lion.js")

    assert "installChartPaneHost" in host
    assert "chart-legend" in host
    assert "#chart-host .chart-card" in host
    assert "canvas, .chart-slot" in host
    assert 'document.createElement("wa-tag")' in webawesome
    assert 'document.createElement("wa-card")' in webawesome
    assert "installChartPaneHost" in webawesome
    assert 'document.createElement("sp-card")' in spectrum
    assert 'document.createElement("ui5-card")' in ui5
    assert 'document.createElement("ui5-card-header")' in ui5
    assert 'document.createElement("ui5-tag")' in ui5
    assert "surface-vaadin-chart-card" in vaadin
    assert "surface-lion-chart-card" in lion
    assert ".chart-card[data-surface-wrapped]" in shared
    assert "[data-surface-legend]" in shared
    for forbidden in ("renderTable", "drawChart", "openFilterMenu", "kabutanUrl"):
        assert forbidden not in host
        assert forbidden not in webawesome


@pytest.mark.unit
def test_library_font_tokens_cover_surface_text_and_chart_labels() -> None:
    theme = _text(_PROTOTYPE / "src" / "theme.js")
    bridge = _text(_PROTOTYPE / "src" / "font-bridge.js")
    shared = _text(_PROTOTYPE / "src" / "surface-shared.css")
    webawesome = _text(_PROTOTYPE / "src" / "surface.css")
    spectrum = _text(_PROTOTYPE / "src" / "surfaces" / "spectrum.css")
    ui5_css = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.css")
    ui5_js = _text(_PROTOTYPE / "src" / "surfaces" / "ui5.js")
    vaadin = _text(_PROTOTYPE / "src" / "surfaces" / "vaadin.css")
    lion = _text(_PROTOTYPE / "src" / "surfaces" / "lion.css")

    assert '"./font-bridge.js"' in theme
    assert "wa-dark" in theme
    assert "px sans-serif" in bridge
    assert "--surface-font-family" in bridge
    assert "--surface-chart-font-size" in bridge
    assert "productionChartBg" in bridge
    assert '"--chart-bg"' in bridge
    assert "var(--surface-font-family)" in shared
    assert ".chart-card h4" in shared
    assert "td.num" in shared
    assert "var(--wa-font-family-body)" in webawesome
    assert "var(--wa-font-family-code)" in webawesome
    assert "var(--wa-font-size-xs)" in webawesome
    assert "var(--wa-font-size-3xs)" in webawesome
    assert "html.wa-dark" in webawesome
    assert "--wa-color-surface-default: var(--surface-overlay)" in webawesome
    assert "color-mix(in oklab, var(--wa-color-gray-05), black 20%)" in webawesome
    assert "Yu Gothic" not in webawesome
    assert "var(--spectrum-cjk-font-family-stack)" in spectrum
    assert "var(--spectrum-code-font-family)" in spectrum
    assert "var(--spectrum-font-size-75)" in spectrum
    assert "--spectrum-background-base-color" in spectrum
    assert "var(--sapFontFamily)" in ui5_css
    assert "var(--sapFontHeaderFamily)" in ui5_css
    assert "var(--sapFontSmallSize)" in ui5_css
    assert "--sapBackgroundColor" in ui5_css
    assert "parameters-bundle.css" in ui5_js
    assert "var(--lumo-font-family)" in vaadin
    assert "var(--lumo-font-size-xs)" in vaadin
    assert "var(--lumo-font-size-xxs)" in vaadin
    assert "--chart-bg: var(--lumo-shade)" in vaadin
    assert "--surface-font" not in lion
    assert "--chart-bg: var(--bg)" in lion


@pytest.mark.unit
def test_graph_keeps_production_series_math() -> None:
    production_app = _text(_PRODUCTION / "app.js")
    generated_app = _text(_PROTOTYPE / "public" / "production-app.js")

    for blob in (production_app, generated_app):
        assert 'const CHART_BG = "rgb(9,7,32)"' in blob
        assert 'const RS_POS = "39,255,104"' in blob
        assert 'const RS_NEG = "255,39,115"' in blob
        assert "function drawChart" in blob
    assert generated_app == production_app
