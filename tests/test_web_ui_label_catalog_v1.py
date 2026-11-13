"""Draft Web UI label catalog stays unadopted and internally consistent."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_CATALOG = _REPO / "docs" / "operations" / "web_ui_label_catalog_v1.yaml"
_INDEX = _REPO / "docs" / "INDEX.md"

_REQUIRED_IDS = {
    "code",
    "name",
    "favorite",
    "price_text",
    "z_turnover_60",
    "rs_acceleration_zscore",
    "rs_acceleration",
    "rs31",
    "rs63",
    "rs126",
    "rs252",
    "rs_sma75",
    "event_news_bundle",
    "research_prompt_block",
}


@pytest.mark.unit
def test_label_catalog_is_draft_and_does_not_close_track_d() -> None:
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    assert data["status"] == "draft_first"
    assert data["adopted"] is False
    assert data["replaces_web_ui_v1"] is False
    assert data["applied_to_screen"] is True
    assert data["closes_live_gate_5d"] is False
    index = _INDEX.read_text(encoding="utf-8")
    assert "web_ui_label_catalog_v1.md" in index
    assert "未採用" in index.split("web_ui_label_catalog_v1.md")[0][-80:]


@pytest.mark.unit
def test_label_catalog_unifies_chart_names_and_keeps_explanations() -> None:
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    entries = data["entries"]
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert _REQUIRED_IDS <= set(ids)
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id["rs31"]["current"]["table"] == "31日"
    assert by_id["rs31"]["current"]["chart_legend"] == "RS31"
    assert by_id["rs_sma75"]["current"]["table"] == "SMA75 RS"
    assert by_id["rs_sma75"]["current"]["chart_legend"] == "SMA75RS"
    assert by_id["z_turnover_60"]["current"]["table"] == "Zscore"
    for entry in entries:
        assert entry["formal_name"].strip()
        assert entry["explanation"].strip()
        proposed = entry["proposed"]
        assert proposed["table"].strip()
        if entry["on_chart"]:
            assert proposed["table"] == proposed["chart_legend"] == proposed["chart_hover"]
        else:
            assert proposed["chart_legend"] is None
            assert proposed["chart_hover"] is None


@pytest.mark.unit
def test_label_catalog_proposed_names_avoid_glossary_jargon() -> None:
    """Revision 2: proposed labels use everyday words.

    Jargon such as 相対力 / ベンチ / 断面 lives only in ``internal_name``
    and in explanations, never in the proposed table/legend/hover labels.
    The short ideal names keep ``RS``. ``formal_name`` follows the short
    review-table column, which keeps Zscore.
    """
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    assert data["revision"] >= 2
    glossary = data["glossary"]
    assert glossary
    avoid_terms: list[str] = []
    for item in glossary:
        assert item["avoid"] and item["use"].strip() and item["why"].strip()
        avoid_terms.extend(item["avoid"])
    assert "相対力" in avoid_terms
    assert "ベンチ" in avoid_terms
    for entry in data["entries"]:
        assert entry["internal_name"].strip(), entry["id"]
        surfaces = [
            entry["proposed"][key]
            for key in ("table", "chart_legend", "chart_hover")
            if entry["proposed"][key] is not None
        ]
        for text in surfaces:
            for term in avoid_terms:
                if term == "RS":
                    continue
                assert term not in text, (entry["id"], term, text)


@pytest.mark.unit
def test_label_catalog_index_relative_family_is_single_sourced() -> None:
    """定義・符号・単位は families.index_relative に一度だけ書き、各列はそれを前置する。"""
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    family = data["families"]["index_relative"]
    assert family["label"] == "指数比"
    core = family["explanation"]
    assert "リターン" in core and "下がればマイナス" in core
    assert "引き算" in core
    assert "株価が下がっていても" in core
    assert "+0.1" in core and "%表示ではない" in core
    by_id = {entry["id"]: entry for entry in data["entries"]}
    members = family["applies_to"]
    assert set(members) == {"rs31", "rs63", "rs126", "rs252", "rs_sma75"}
    expected_labels = {
        "rs31": "31日RS",
        "rs63": "63日RS",
        "rs126": "126日RS",
        "rs252": "252日RS",
        "rs_sma75": "75移動平均RS",
    }
    for entry_id in members:
        entry = by_id[entry_id]
        assert entry["family"] == "index_relative", entry_id
        assert entry["proposed"]["table"] == expected_labels[entry_id], entry_id
        assert "+0.1" not in entry["explanation"], entry_id


@pytest.mark.unit
def test_label_catalog_explanations_are_user_facing_only() -> None:
    """ツールチップ文（explanation）に製品・仕組みの事実を混ぜない。それらは spec_notes に置く。

    既定で隠れている列や、表・凡例に出ない語（対象銘柄）も同じ形式で持つ。
    """
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    spec_only = ("XLSX", "既定の表", "既定では隠れ", "candle_labels", "Z÷5", "同じ値", "システム内の呼び名", "RS31", "SMA75", "Zscore")
    surfaces = set()
    for entry in data["entries"]:
        assert entry["surface"].strip(), entry["id"]
        surfaces.add(entry["surface"])
        assert isinstance(entry["spec_notes"], list), entry["id"]
        for term in spec_only:
            assert term not in entry["explanation"], (entry["id"], term)
    by_id = {entry["id"]: entry for entry in data["entries"]}
    for entry_id in ("beta_adjusted_rs", "information_ratio", "perfect_order_days", "price_change_pct", "turnover_ma_ratio_60"):
        entry = by_id[entry_id]
        assert entry["default_visible"] is False
        assert entry["surface"] == "table_column_optional"
        assert entry["explanation"].strip()
    core = by_id["core_universe"]
    assert core["surface"] == "term_button"
    assert core["proposed"]["table"] == "対象銘柄"
    assert "コアユニバース" not in core["explanation"]
    assert any("コアユニバース" in note for note in core["spec_notes"])
    assert {"table_column", "table_column_and_chart", "toolbar", "filter_switch", "web_pane_tab"} <= surfaces


_MD = _REPO / "docs" / "operations" / "web_ui_label_catalog_v1.md"


def _squash(text: str) -> str:
    return "".join(text.split())


@pytest.mark.unit
def test_label_catalog_markdown_copy_mirrors_yaml() -> None:
    """Review copy must contain every canonical field from the YAML SSOT."""
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    md = _MD.read_text(encoding="utf-8")
    squashed = _squash(md)
    for rule in data["reading_rules"]:
        assert _squash(rule) in squashed, rule[:40]
    for note in data["implementation_notes"]:
        assert _squash(note) in squashed, note[:40]
    for item in data["glossary"]:
        for term in item["avoid"]:
            assert term in md, term
        assert item["use"] in md
        assert _squash(item["why"]) in squashed
    assert _squash(data["families"]["index_relative"]["explanation"]) in squashed
    assert _squash(data["families"]["index_relative"]["display"]) in squashed
    assert _squash(data["note"]) in squashed
    for hist in data["revision_history"]:
        assert _squash(hist["summary"]) in squashed
    for entry in data["entries"]:
        assert entry["proposed"]["table"] in md, entry["id"]
        assert entry["formal_name"] in md, entry["id"]
        assert entry["internal_name"] in md, entry["id"]
        assert _squash(entry["explanation"]) in squashed, entry["id"]
        for note in entry["spec_notes"]:
            assert _squash(note) in squashed, (entry["id"], note[:40])


@pytest.mark.unit
def test_screen_uses_catalog_labels_without_spec_notes() -> None:
    """Local screen copy follows proposed labels. Tooltip text stays user-facing."""
    app = ( _REPO / "workers" / "web-ui-static" / "assets" / "app.js").read_text(encoding="utf-8")
    html = (_REPO / "workers" / "web-ui-static" / "assets" / "index.html").read_text(encoding="utf-8")
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    blob = app + "\n" + html
    ideal_labels = {
        "z_turnover_60": "売買代金異常",
        "rs_acceleration_zscore": "RSの加速Z",
        "rs_acceleration": "RSの加速",
        "rs31": "31日RS",
        "rs63": "63日RS",
        "rs126": "126日RS",
        "rs252": "252日RS",
        "rs_sma75": "75移動平均RS",
        "event_news_bundle": "売買代金異常 要因ニュース候補",
        "beta_adjusted_rs": "除β 252日RS",
        "information_ratio": "RSの安定度",
        "perfect_order_days": "ﾊﾟｰﾌｪｸﾄｵｰﾀﾞｰ日数",
    }
    for entry in data["entries"]:
        if entry["id"] in ideal_labels:
            assert entry["proposed"]["table"] == ideal_labels[entry["id"]], entry["id"]
            assert f'label: "{ideal_labels[entry["id"]]}"' in app.replace(
                f'label: "{ideal_labels[entry["id"]]}Z"', ""
            ), entry["id"]
        elif entry["default_visible"] or entry["surface"] == "table_column_optional":
            assert entry["proposed"]["table"] in blob, entry["id"]
        assert entry["explanation"].split()[0] in app or entry["id"] == "web_news_candidates"
    assert "LABEL_TIPS" in app
    assert "data-label-tip" in app
    assert "Z÷5" not in app
    assert "XLSX" not in app.split("const LABEL_TIPS")[1].split("function columnLabelId")[0]
    assert 'name: "お気入り"' in app
