import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/select/select.js";
import "@awesome.me/webawesome/dist/components/option/option.js";
import "@awesome.me/webawesome/dist/components/input/input.js";
import "@awesome.me/webawesome/dist/components/checkbox/checkbox.js";
import "@awesome.me/webawesome/dist/components/progress-bar/progress-bar.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/tag/tag.js";
import "@awesome.me/webawesome/dist/components/divider/divider.js";
import "@awesome.me/webawesome/dist/components/dropdown/dropdown.js";
import "@awesome.me/webawesome/dist/components/dropdown-item/dropdown-item.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "../surface.css";
import "../tabs-ui.js";
import { installHeaderHost } from "../header-host.js";
import { installChromeHost } from "../chrome-host.js";
import { chartSwatch, installChartPaneHost } from "../chart-pane-host.js";

installHeaderHost({
  create() {
    const cell = document.createElement("wa-button");
    cell.size = "xs";
    cell.type = "button";
    return cell;
  },
  sync(cell, meta) {
    cell.appearance = meta.filtered ? "filled-outlined" : "plain";
    cell.variant = meta.sorted || meta.filtered ? "brand" : "neutral";
    cell.withCaret = !!(meta.filterable || meta.numeric);
    cell.title = meta.title;
    let label = cell.querySelector("[data-header-label]");
    if (!label) {
      label = document.createElement("span");
      label.dataset.headerLabel = "";
      cell.prepend(label);
    }
    if (label.textContent !== meta.caption) label.textContent = meta.caption;
  },
});

installChromeHost({
  button(text, opts = {}) {
    const el = document.createElement("wa-button");
    el.size = opts.compact === false ? "m" : "xs";
    el.type = "button";
    el.appearance = opts.strong ? "accent" : "filled-outlined";
    el.variant = opts.strong ? "brand" : "neutral";
    el.textContent = text;
    if (opts.title) el.title = opts.title;
    el.disabled = !!opts.disabled;
    return el;
  },
  setButtonLabel(el, text) {
    if (el.textContent !== text) el.textContent = text;
  },
  select() {
    const el = document.createElement("wa-select");
    el.size = "xs";
    el.appearance = "outlined";
    return el;
  },
  fillSelect(el, items, value) {
    el.replaceChildren(
      ...items.map((item) => {
        const option = document.createElement("wa-option");
        option.value = item.value;
        option.textContent = item.text;
        return option;
      }),
    );
    el.value = value;
  },
  onSelectChange(el, fn) {
    el.addEventListener("change", () => fn(el.value));
    el.addEventListener("wa-change", () => fn(el.value));
  },
  input({ type, placeholder, disabled, value, compact }) {
    const el = document.createElement("wa-input");
    el.type = type === "email" ? "email" : type === "number" ? "number" : "text";
    el.size = compact === false ? "m" : "xs";
    if (placeholder) el.placeholder = placeholder;
    el.disabled = !!disabled;
    if (value) el.value = value;
    return el;
  },
  setInputValue(el, value) {
    if (el.value !== value) el.value = value;
  },
  onInput(el, fn) {
    el.addEventListener("input", () => fn(el.value));
    el.addEventListener("wa-input", () => fn(el.value));
  },
  checkbox(label, checked, disabled) {
    const el = document.createElement("wa-checkbox");
    el.textContent = label;
    el.checked = !!checked;
    el.disabled = !!disabled;
    return el;
  },
  setCheckbox(el, checked, disabled) {
    el.checked = !!checked;
    el.disabled = !!disabled;
  },
  onCheck(el, fn) {
    el.addEventListener("change", () => fn(!!el.checked));
    el.addEventListener("wa-change", () => fn(!!el.checked));
  },
  boot() {
    const card = document.createElement("wa-card");
    const title = document.createElement("div");
    title.slot = "header";
    title.dataset.bootLabel = "";
    const bar = document.createElement("wa-progress-bar");
    card.append(title, bar);
    return card;
  },
  setBoot(el, { label, value }) {
    const text = el.querySelector("[data-boot-label]");
    const bar = el.querySelector("wa-progress-bar");
    if (text && text.textContent !== label) text.textContent = label;
    if (bar) bar.value = value;
  },
  login() {
    const card = document.createElement("wa-card");
    const title = document.createElement("div");
    title.slot = "header";
    title.dataset.loginTitle = "";
    const note = document.createElement("p");
    note.dataset.loginNote = "";
    const formHost = document.createElement("div");
    formHost.dataset.loginForm = "";
    card.append(title, note, formHost);
    return card;
  },
  setLogin(el, { title, note }) {
    const heading = el.querySelector("[data-login-title]");
    const body = el.querySelector("[data-login-note]");
    if (heading) heading.textContent = title;
    if (body) body.textContent = note;
  },
  loginFormHost(el) {
    return el.querySelector("[data-login-form]") || el;
  },
  banner() {
    const el = document.createElement("div");
    const title = document.createElement("strong");
    title.dataset.bannerTitle = "";
    const body = document.createElement("div");
    body.dataset.bannerBody = "";
    el.append(title, body);
    return el;
  },
  setBanner(el, { title, body }) {
    const heading = el.querySelector("[data-banner-title]");
    const text = el.querySelector("[data-banner-body]");
    if (heading) heading.textContent = title;
    if (text) text.textContent = body;
  },
  splitterHandle() {
    return document.createElement("div");
  },
});

installChartPaneHost({
  legendItem({ label, swatchStyle, swatchClass }) {
    const el = document.createElement("wa-tag");
    el.size = "xs";
    el.variant = "neutral";
    el.appearance = "outlined";
    el.append(chartSwatch({ swatchStyle, swatchClass }), document.createTextNode(label));
    return el;
  },
  chartCard() {
    const el = document.createElement("wa-card");
    el.appearance = "outlined";
    const title = document.createElement("div");
    title.slot = "header";
    title.dataset.chartTitle = "";
    const hover = document.createElement("div");
    hover.dataset.chartHover = "";
    const media = document.createElement("div");
    media.dataset.chartCanvas = "";
    el.append(title, hover, media);
    return el;
  },
  setChartCard(el, { title, hover, selected, hovered }) {
    const heading = el.querySelector("[data-chart-title]");
    const text = el.querySelector("[data-chart-hover]");
    if (heading && heading.textContent !== title) heading.textContent = title;
    if (text && text.innerHTML !== hover) text.innerHTML = hover || "";
    el.classList.toggle("is-selected", !!selected);
    el.classList.toggle("is-hover", !!hovered);
    const appearance = selected ? "accent" : hovered ? "filled-outlined" : "outlined";
    if (el.appearance !== appearance) el.appearance = appearance;
  },
  chartCanvasHost(el) {
    return el.querySelector("[data-chart-canvas]");
  },
});
