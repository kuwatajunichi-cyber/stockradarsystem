import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/select/select.js";
import "@awesome.me/webawesome/dist/components/option/option.js";
import "@awesome.me/webawesome/dist/components/input/input.js";
import "@awesome.me/webawesome/dist/components/checkbox/checkbox.js";
import "@awesome.me/webawesome/dist/components/progress-bar/progress-bar.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/tag/tag.js";
import "@awesome.me/webawesome/dist/components/tab-group/tab-group.js";
import "@awesome.me/webawesome/dist/components/tab/tab.js";
import "@awesome.me/webawesome/dist/components/tab-panel/tab-panel.js";
import "@awesome.me/webawesome/dist/components/divider/divider.js";
import "@awesome.me/webawesome/dist/components/dropdown/dropdown.js";
import "@awesome.me/webawesome/dist/components/dropdown-item/dropdown-item.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "./font-bridge.js";
import "./theme.css";
import {
  applyConditionalFormatting,
  cfRangeForLabel,
  numberCellFormat,
  priceTone,
} from "./conditional-format.js";

document.documentElement.classList.add("wa-dark");

function button(text, opts = {}) {
  const el = document.createElement("wa-button");
  el.size = opts.compact === false ? "m" : "xs";
  el.type = opts.type || "button";
  el.appearance = opts.strong ? "accent" : opts.plain ? "plain" : "filled-outlined";
  el.variant = opts.strong || opts.brand ? "brand" : "neutral";
  el.textContent = text;
  if (opts.title) el.title = opts.title;
  el.disabled = !!opts.disabled;
  if (opts.href) {
    el.href = opts.href;
    el.target = opts.target || "_blank";
    el.rel = "noopener";
  }
  return el;
}

function setButtonLabel(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

function select(opts = {}) {
  const el = document.createElement("wa-select");
  el.size = opts.compact === false ? "m" : "xs";
  el.appearance = "outlined";
  return el;
}

function fillSelect(el, items, value) {
  const encoded = JSON.stringify(items);
  if (el.dataset.surfaceItems !== encoded) {
    el.replaceChildren(
      ...items.map((item) => {
        const option = document.createElement("wa-option");
        option.value = item.value;
        option.textContent = item.text;
        return option;
      }),
    );
    el.dataset.surfaceItems = encoded;
  }
  if (el.value !== value) el.value = value;
}

function onSelectChange(el, fn) {
  const handler = () => fn(el.value);
  el.addEventListener("change", handler);
  el.addEventListener("wa-change", handler);
}

function input({ type, placeholder, disabled, value, compact, id } = {}) {
  const el = document.createElement("wa-input");
  el.type = type === "email" ? "email" : type === "number" ? "number" : "text";
  el.size = compact === false ? "m" : "xs";
  if (placeholder) el.placeholder = placeholder;
  el.disabled = !!disabled;
  if (value != null) el.value = value;
  if (id) el.id = id;
  return el;
}

function checkbox(label, checked, disabled) {
  const el = document.createElement("wa-checkbox");
  el.textContent = label;
  el.checked = !!checked;
  el.disabled = !!disabled;
  return el;
}

function onCheck(el, fn) {
  const handler = () => fn(!!el.checked);
  el.addEventListener("change", handler);
  el.addEventListener("wa-change", handler);
}

function tag(label, { swatchStyle, swatchClass } = {}) {
  const el = document.createElement("wa-tag");
  el.size = "xs";
  el.variant = "neutral";
  el.appearance = "outlined";
  const swatch = document.createElement("i");
  swatch.setAttribute("aria-hidden", "true");
  if (swatchClass) swatch.className = swatchClass;
  if (swatchStyle) swatch.setAttribute("style", swatchStyle);
  const text = document.createElement("span");
  text.className = "surface-label-compact";
  const glyph = document.createElement("span");
  glyph.className = "surface-label-compact-text";
  glyph.textContent = label;
  text.append(glyph);
  el.append(swatch, text);
  return el;
}

function chartCard() {
  const el = document.createElement("wa-card");
  el.appearance = "outlined";
  const head = document.createElement("div");
  head.slot = "header";
  head.className = "chart-card-head";
  const title = document.createElement("div");
  title.dataset.chartTitle = "";
  const fav = document.createElement("div");
  fav.dataset.chartFav = "";
  head.append(title, fav);
  const hover = document.createElement("div");
  hover.className = "hover";
  hover.dataset.chartHover = "";
  const media = document.createElement("div");
  media.className = "chart-slot";
  media.dataset.chartCanvas = "";
  el.append(head, hover, media);
  return el;
}

function headerButton({ caption, title, sorted, filtered }) {
  const el = document.createElement("wa-button");
  el.size = "xs";
  el.type = "button";
  el.dataset.surfaceHeader = "";
  el.appearance = filtered ? "filled-outlined" : "plain";
  el.variant = sorted || filtered ? "brand" : "neutral";
  el.withCaret = true;
  el.title = title || "";
  const label = document.createElement("span");
  label.className = "th-label";
  label.dataset.headerLabel = "";
  const glyph = document.createElement("span");
  glyph.className = "surface-label-compact-text";
  glyph.textContent = caption;
  label.append(glyph);
  el.prepend(label);
  return el;
}

function tabGroup() {
  const el = document.createElement("wa-tab-group");
  el.setAttribute("activation", "auto");
  return el;
}

function tab({ panel, label, title, disabled, active, candidate }) {
  const el = document.createElement("wa-tab");
  el.setAttribute("panel", panel);
  el.textContent = label;
  if (title) el.title = title;
  el.disabled = !!disabled;
  if (active) el.setAttribute("active", "");
  if (candidate) el.classList.add("is-candidate");
  return el;
}

function tabPanel(name, active) {
  const el = document.createElement("wa-tab-panel");
  el.setAttribute("name", name);
  el.setAttribute("aria-hidden", "true");
  if (active) el.setAttribute("active", "");
  return el;
}

window.StockRadarChrome = {
  button,
  setButtonLabel,
  select,
  fillSelect,
  onSelectChange,
  input,
  checkbox,
  onCheck,
  tag,
  chartCard,
  headerButton,
  tabGroup,
  tab,
  tabPanel,
  applyConditionalFormatting,
  numberCellFormat,
  cfRangeForLabel,
  priceTone,
};