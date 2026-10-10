import "@spectrum-web-components/theme/sp-theme.js";
import "@spectrum-web-components/theme/theme-dark.js";
import "@spectrum-web-components/theme/scale-medium.js";
import "@spectrum-web-components/tabs/sp-tabs.js";
import "@spectrum-web-components/tabs/sp-tab.js";
import "@spectrum-web-components/tabs/sp-tab-panel.js";
import "@spectrum-web-components/table/sp-table-head-cell.js";
import "@spectrum-web-components/action-button/sp-action-button.js";
import "@spectrum-web-components/button/sp-button.js";
import "@spectrum-web-components/picker/sp-picker.js";
import "@spectrum-web-components/menu/sp-menu-item.js";
import "@spectrum-web-components/progress-bar/sp-progress-bar.js";
import "@spectrum-web-components/textfield/sp-textfield.js";
import "@spectrum-web-components/checkbox/sp-checkbox.js";
import "@spectrum-web-components/divider/sp-divider.js";
import "@spectrum-web-components/card/sp-card.js";
import "./spectrum.css";
import { installTabHost } from "../tab-host.js";
import { installHeaderHost } from "../header-host.js";
import { installChromeHost } from "../chrome-host.js";
import { chartSwatch, installChartPaneHost } from "../chart-pane-host.js";

function ensureSpectrumTheme() {
  const apply = () => {
    if (document.querySelector("sp-theme[data-surface-theme]")) return;
    const theme = document.createElement("sp-theme");
    theme.dataset.surfaceTheme = "spectrum";
    theme.setAttribute("system", "spectrum");
    theme.setAttribute("color", "dark");
    theme.setAttribute("scale", "medium");
    const nodes = [...document.body.childNodes];
    document.body.append(theme);
    for (const node of nodes) theme.append(node);
  };
  if (document.body) apply();
  else document.addEventListener("DOMContentLoaded", apply, { once: true });
}

function panelValue(index) {
  return `surface-kabutan-panel-${index}`;
}

ensureSpectrumTheme();
installTabHost({
  createGroup() {
    const group = document.createElement("sp-tabs");
    group.setAttribute("compact", "");
    group.setAttribute("quiet", "");
    return group;
  },
  sync(group, buttons, sourceButtons) {
    const nodes = [];
    let active = "";
    buttons.forEach((button, index) => {
      const value = panelValue(index);
      const tab = document.createElement("sp-tab");
      tab.label = button.textContent.trim();
      tab.value = value;
      tab.title = button.title;
      tab.disabled = button.disabled;
      if (button.hasAttribute("data-cand")) tab.classList.add("is-candidate");
      const panel = document.createElement("sp-tab-panel");
      panel.value = value;
      nodes.push(tab, panel);
      sourceButtons.set(value, button);
      if (button.classList.contains("active")) active = value;
    });
    group.replaceChildren(...nodes);
    const next = active || (buttons.length ? panelValue(0) : "");
    const applySelected = () => {
      if (group.querySelector("sp-tab")) group.selected = next;
    };
    queueMicrotask(applySelected);
    requestAnimationFrame(applySelected);
  },
  bind(group, getButtons, activate) {
    group.addEventListener("change", () => {
      activate(getButtons().get(group.selected));
    });
  },
});

installHeaderHost({
  create() {
    return document.createElement("sp-table-head-cell");
  },
  sync(cell, meta) {
    cell.sortable = meta.numeric;
    cell.sortDirection = meta.sortDirection || undefined;
    cell.title = meta.title;
    let label = cell.querySelector("[data-header-label]");
    if (!label) {
      label = document.createElement("span");
      label.dataset.headerLabel = "";
      cell.prepend(label);
    }
    if (label.textContent !== meta.label) label.textContent = meta.label;
    let filter = cell.querySelector("[data-header-filter]");
    if ((meta.filterable || meta.numeric) && !filter) {
      filter = document.createElement("sp-action-button");
      filter.quiet = true;
      filter.textContent = "▼";
      filter.dataset.headerFilter = "";
      cell.append(filter);
    }
  },
});

installChromeHost({
  button(text, opts = {}) {
    const el = document.createElement("sp-button");
    el.size = opts.compact === false ? "m" : "s";
    el.variant = opts.strong ? "accent" : "secondary";
    el.treatment = opts.strong ? "fill" : "outline";
    el.textContent = text;
    if (opts.title) el.title = opts.title;
    el.disabled = !!opts.disabled;
    return el;
  },
  setButtonLabel(el, text) {
    if (el.textContent !== text) el.textContent = text;
  },
  select() {
    return document.createElement("sp-picker");
  },
  fillSelect(el, items, value) {
    el.replaceChildren(
      ...items.map((item) => {
        const option = document.createElement("sp-menu-item");
        option.value = item.value;
        option.textContent = item.text;
        return option;
      }),
    );
    el.value = value;
  },
  onSelectChange(el, fn) {
    el.addEventListener("change", () => fn(el.value));
  },
  input({ type, placeholder, disabled, value }) {
    const el = document.createElement("sp-textfield");
    if (type === "number") el.type = "number";
    else if (type === "email") el.type = "email";
    else el.type = "text";
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
  },
  checkbox(label, checked, disabled) {
    const el = document.createElement("sp-checkbox");
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
  },
  boot() {
    const card = document.createElement("sp-card");
    const bar = document.createElement("sp-progress-bar");
    bar.label = "起動オーバーレイ";
    bar.slot = "footer";
    card.append(bar);
    return card;
  },
  setBoot(el, { label, value }) {
    const bar = el.querySelector("sp-progress-bar");
    if (bar) {
      bar.label = label;
      bar.progress = value;
    }
  },
  login() {
    const card = document.createElement("sp-card");
    const title = document.createElement("div");
    title.slot = "heading";
    title.dataset.loginTitle = "";
    const formHost = document.createElement("div");
    formHost.slot = "footer";
    formHost.dataset.loginForm = "";
    const note = document.createElement("div");
    note.dataset.loginNote = "";
    formHost.append(note);
    card.append(title, formHost);
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
    const el = document.createElement("sp-action-button");
    el.quiet = true;
    el.size = "s";
    el.append(chartSwatch({ swatchStyle, swatchClass }), document.createTextNode(label));
    return el;
  },
  chartCard() {
    const el = document.createElement("sp-card");
    el.variant = "quiet";
    const title = document.createElement("div");
    title.slot = "heading";
    title.dataset.chartTitle = "";
    const hover = document.createElement("div");
    hover.slot = "subheading";
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
    el.selected = !!selected;
    el.classList.toggle("is-hover", !!hovered);
  },
  chartCanvasHost(el) {
    return el.querySelector("[data-chart-canvas]");
  },
});
