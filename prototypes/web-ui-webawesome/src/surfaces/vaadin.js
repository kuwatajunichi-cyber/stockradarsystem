import "@vaadin/vaadin-lumo-styles/color-global.js";
import "@vaadin/vaadin-lumo-styles/typography-global.js";
import "@vaadin/tabs";
import "@vaadin/button";
import "@vaadin/select";
import "@vaadin/text-field";
import "@vaadin/email-field";
import "@vaadin/checkbox";
import "@vaadin/progress-bar";
import "@vaadin/horizontal-layout";
import "./vaadin.css";
import { installTabHost } from "../tab-host.js";
import { installHeaderHost } from "../header-host.js";
import { installChromeHost } from "../chrome-host.js";
import { chartSwatch, installChartPaneHost } from "../chart-pane-host.js";

installTabHost({
  createGroup() {
    return document.createElement("vaadin-tabs");
  },
  sync(group, buttons, sourceButtons) {
    const tabs = buttons.map((button, index) => {
      const tab = document.createElement("vaadin-tab");
      tab.textContent = button.textContent.trim();
      tab.title = button.title;
      tab.disabled = button.disabled;
      if (button.hasAttribute("data-cand")) tab.classList.add("is-candidate");
      sourceButtons.set(String(index), button);
      return tab;
    });
    group.replaceChildren(...tabs);
    const active = buttons.findIndex((button) => button.classList.contains("active"));
    group.selected = active >= 0 ? active : 0;
  },
  bind(group, getButtons, activate) {
    const selectFromEvent = (event) => {
      const tab = event.composedPath().find((node) => node.localName === "vaadin-tab");
      if (!tab) return;
      const index = [...group.children].indexOf(tab);
      activate(getButtons().get(String(index)));
    };
    group.addEventListener("selected-changed", selectFromEvent);
    group.addEventListener("click", selectFromEvent);
  },
});

installHeaderHost({
  create() {
    const cell = document.createElement("div");
    cell.className = "surface-vaadin-header";
    const label = document.createElement("vaadin-button");
    label.setAttribute("theme", "tertiary-inline small");
    label.dataset.headerLabel = "";
    cell.append(label);
    return cell;
  },
  sync(cell, meta) {
    const theme = meta.sorted || meta.filtered
      ? "primary tertiary-inline small"
      : "tertiary-inline small";
    const label = cell.querySelector("[data-header-label]");
    if (label) {
      if (label.getAttribute("theme") !== theme) label.setAttribute("theme", theme);
      if (label.textContent !== meta.caption) label.textContent = meta.caption;
      label.title = meta.title;
    }
    let filter = cell.querySelector("[data-header-filter]");
    if ((meta.filterable || meta.numeric) && !filter) {
      filter = document.createElement("vaadin-button");
      filter.setAttribute("theme", "tertiary-inline small");
      filter.textContent = "▼";
      filter.dataset.headerFilter = "";
      cell.append(filter);
    }
  },
});

installChromeHost({
  button(text, opts = {}) {
    const el = document.createElement("vaadin-button");
    const theme = [opts.strong ? "primary" : "", opts.compact === false ? "" : "small"]
      .filter(Boolean)
      .join(" ");
    if (theme) el.setAttribute("theme", theme);
    el.textContent = text;
    if (opts.title) el.title = opts.title;
    el.disabled = !!opts.disabled;
    return el;
  },
  setButtonLabel(el, text) {
    if (el.textContent !== text) el.textContent = text;
  },
  select() {
    return document.createElement("vaadin-select");
  },
    fillSelect(el, items, value) {
      const next = items.map((item) => ({ label: item.text, value: item.value }));
      const encoded = JSON.stringify(next);
      if (el.dataset.surfaceItems === encoded && el.value === value) return;
      el.dataset.surfaceItems = encoded;
      el.items = next;
      el.value = value;
    },
  onSelectChange(el, fn) {
    el.addEventListener("value-changed", () => fn(el.value));
    el.addEventListener("change", () => fn(el.value));
  },
  input({ type, placeholder, disabled, value }) {
    const el = document.createElement(type === "email" ? "vaadin-email-field" : "vaadin-text-field");
    if (type === "number") el.type = "number";
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
    el.addEventListener("value-changed", () => fn(el.value));
  },
  checkbox(label, checked, disabled) {
    const el = document.createElement("vaadin-checkbox");
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
    el.addEventListener("change", () => fn(!!el.checked));
  },
  boot() {
    const box = document.createElement("div");
    box.className = "surface-boot-card";
    const label = document.createElement("p");
    label.dataset.bootLabel = "";
    const bar = document.createElement("vaadin-progress-bar");
    box.append(label, bar);
    return box;
  },
  setBoot(el, { label, value }) {
    const text = el.querySelector("[data-boot-label]");
    const bar = el.querySelector("vaadin-progress-bar");
    if (text) text.textContent = label;
    if (bar) bar.value = value / 100;
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
    const body = document.createElement("span");
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
    const el = document.createElement("vaadin-button");
    el.setAttribute("theme", "tertiary-inline small");
    el.append(chartSwatch({ swatchStyle, swatchClass }), document.createTextNode(label));
    return el;
  },
  chartCard() {
    const el = document.createElement("div");
    el.className = "surface-vaadin-chart-card";
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
