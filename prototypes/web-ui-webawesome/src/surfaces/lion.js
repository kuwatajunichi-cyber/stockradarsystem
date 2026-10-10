import "@lion/ui/define/lion-tabs.js";
import "@lion/ui/define/lion-button.js";
import "@lion/ui/define/lion-input.js";
import "@lion/ui/define/lion-input-email.js";
import "@lion/ui/define/lion-checkbox.js";
import "@lion/ui/define/lion-select.js";
import "./lion.css";
import { installTabHost } from "../tab-host.js";
import { installHeaderHost } from "../header-host.js";
import { installChromeHost } from "../chrome-host.js";
import { chartSwatch, installChartPaneHost } from "../chart-pane-host.js";

installTabHost({
  createGroup() {
    return document.createElement("lion-tabs");
  },
  sync(group, buttons, sourceButtons) {
    const nodes = [];
    buttons.forEach((button, index) => {
      const tab = document.createElement("button");
      tab.slot = "tab";
      tab.type = "button";
      tab.textContent = button.textContent.trim();
      tab.title = button.title;
      tab.disabled = button.disabled;
      if (button.hasAttribute("data-cand")) tab.classList.add("is-candidate");
      const panel = document.createElement("div");
      panel.slot = "panel";
      panel.setAttribute("aria-hidden", "true");
      panel.style.setProperty("display", "none", "important");
      nodes.push(tab, panel);
      sourceButtons.set(String(index), button);
    });
    group.replaceChildren(...nodes);
    const active = buttons.findIndex((button) => button.classList.contains("active"));
    group.selectedIndex = active >= 0 ? active : 0;
  },
  bind(group, getButtons, activate) {
    group.addEventListener("selected-changed", () => {
      activate(getButtons().get(String(group.selectedIndex)));
    });
  },
});

installHeaderHost({
  create() {
    const cell = document.createElement("div");
    cell.className = "surface-lion-header";
    const label = document.createElement("lion-button");
    label.type = "button";
    label.dataset.headerLabel = "";
    cell.append(label);
    return cell;
  },
  sync(cell, meta) {
    const label = cell.querySelector("[data-header-label]");
    if (label && label.textContent !== meta.caption) label.textContent = meta.caption;
    if (label) label.title = meta.title;
    let filter = cell.querySelector("[data-header-filter]");
    if ((meta.filterable || meta.numeric) && !filter) {
      filter = document.createElement("lion-button");
      filter.type = "button";
      filter.textContent = "▼";
      filter.dataset.headerFilter = "";
      cell.append(filter);
    }
  },
});

installChromeHost({
  button(text, opts = {}) {
    const el = document.createElement("lion-button");
    el.type = "button";
    el.textContent = text;
    if (opts.title) el.title = opts.title;
    el.disabled = !!opts.disabled;
    return el;
  },
  setButtonLabel(el, text) {
    if (el.textContent !== text) el.textContent = text;
  },
  select() {
    const el = document.createElement("lion-select");
    const native = document.createElement("select");
    native.slot = "input";
    el.append(native);
    return el;
  },
  fillSelect(el, items, value) {
    const native = el.querySelector("select") || el;
    native.replaceChildren(
      ...items.map((item) => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.text;
        option.selected = item.value === value;
        return option;
      }),
    );
    native.value = value;
    if ("modelValue" in el) el.modelValue = value;
  },
  onSelectChange(el, fn) {
    const native = el.querySelector("select") || el;
    native.addEventListener("change", () => fn(native.value));
    el.addEventListener("model-value-changed", () => fn(el.modelValue ?? native.value));
  },
  input({ type, placeholder, disabled, value }) {
    const el = document.createElement(type === "email" ? "lion-input-email" : "lion-input");
    if (placeholder) el.label = placeholder;
    el.disabled = !!disabled;
    if (value) el.modelValue = value;
    return el;
  },
  setInputValue(el, value) {
    if (el.modelValue !== value) el.modelValue = value;
  },
  onInput(el, fn) {
    el.addEventListener("model-value-changed", () => fn(el.modelValue ?? ""));
  },
  checkbox(label, checked, disabled) {
    const el = document.createElement("lion-checkbox");
    el.label = label;
    el.checked = !!checked;
    el.disabled = !!disabled;
    return el;
  },
  setCheckbox(el, checked, disabled) {
    el.checked = !!checked;
    el.disabled = !!disabled;
  },
  onCheck(el, fn) {
    el.addEventListener("checked-changed", () => fn(!!el.checked));
    el.addEventListener("model-value-changed", () => fn(!!el.checked));
  },
  boot() {
    const box = document.createElement("div");
    box.className = "surface-boot-card";
    const label = document.createElement("p");
    label.dataset.bootLabel = "";
    const bar = document.createElement("progress");
    bar.max = 100;
    box.append(label, bar);
    return box;
  },
  setBoot(el, { label, value }) {
    const text = el.querySelector("[data-boot-label]");
    const bar = el.querySelector("progress");
    if (text) text.textContent = label;
    if (bar) bar.value = value;
  },
  login() {
    const box = document.createElement("div");
    box.className = "surface-login-card";
    const title = document.createElement("h1");
    title.dataset.loginTitle = "";
    const note = document.createElement("p");
    note.dataset.loginNote = "";
    const formHost = document.createElement("div");
    formHost.dataset.loginForm = "";
    box.append(title, note, formHost);
    return box;
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
    const el = document.createElement("lion-button");
    el.type = "button";
    el.append(chartSwatch({ swatchStyle, swatchClass }), document.createTextNode(label));
    return el;
  },
  chartCard() {
    const el = document.createElement("div");
    el.className = "surface-lion-chart-card";
    const title = document.createElement("strong");
    title.dataset.chartTitle = "";
    const hover = document.createElement("span");
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
  },
  chartCanvasHost(el) {
    return el.querySelector("[data-chart-canvas]");
  },
});
