import "@ui5/webcomponents-theming/dist/css/themes/sap_horizon_dark/parameters-bundle.css";
import "@ui5/webcomponents/dist/Assets.js";
import "@ui5/webcomponents/dist/TabContainer.js";
import "@ui5/webcomponents/dist/Tab.js";
import "@ui5/webcomponents/dist/TableHeaderCell.js";
import "@ui5/webcomponents/dist/Button.js";
import "@ui5/webcomponents/dist/Select.js";
import "@ui5/webcomponents/dist/Option.js";
import "@ui5/webcomponents/dist/Input.js";
import "@ui5/webcomponents/dist/CheckBox.js";
import "@ui5/webcomponents/dist/ProgressIndicator.js";
import "@ui5/webcomponents/dist/Bar.js";
import "@ui5/webcomponents/dist/Title.js";
import "@ui5/webcomponents/dist/Panel.js";
import "@ui5/webcomponents/dist/Card.js";
import "@ui5/webcomponents/dist/CardHeader.js";
import "@ui5/webcomponents/dist/Tag.js";
import { setTheme } from "@ui5/webcomponents-base/dist/config/Theme.js";
import "./ui5.css";
import { installTabHost } from "../tab-host.js";
import { installHeaderHost } from "../header-host.js";
import { installChromeHost } from "../chrome-host.js";
import { chartSwatch, installChartPaneHost } from "../chart-pane-host.js";

setTheme("sap_horizon_dark");

installTabHost({
  createGroup() {
    const group = document.createElement("ui5-tabcontainer");
    group.collapsed = true;
    group.headerBackgroundDesign = "Transparent";
    group.contentBackgroundDesign = "Transparent";
    return group;
  },
  sync(group, buttons, sourceButtons) {
    const tabs = buttons.map((button, index) => {
      const tab = document.createElement("ui5-tab");
      tab.text = button.textContent.trim();
      tab.title = button.title;
      tab.disabled = button.disabled;
      tab.selected = button.classList.contains("active");
      if (button.hasAttribute("data-cand")) tab.classList.add("is-candidate");
      sourceButtons.set(String(index), button);
      return tab;
    });
    if (tabs.length && !tabs.some((tab) => tab.selected)) tabs[0].selected = true;
    group.replaceChildren(...tabs);
  },
  bind(group, getButtons, activate) {
    group.addEventListener("tab-select", (event) => {
      const index = event.detail?.tabIndex;
      activate(getButtons().get(String(index)));
    });
  },
});

installHeaderHost({
  create() {
    return document.createElement("ui5-table-header-cell");
  },
  sync(cell, meta) {
    cell.sortIndicator = meta.sorted
      ? meta.sortDirection === "asc"
        ? "Ascending"
        : "Descending"
      : "None";
    cell.horizontalAlign = meta.numeric ? "End" : "Start";
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
      filter = document.createElement("ui5-button");
      filter.design = "Transparent";
      filter.textContent = "▼";
      filter.dataset.headerFilter = "";
      filter.slot = "action";
      cell.append(filter);
    }
  },
});

installChromeHost({
  button(text, opts = {}) {
    const el = document.createElement("ui5-button");
    el.design = opts.strong ? "Emphasized" : "Default";
    el.textContent = text;
    if (opts.title) el.title = opts.title;
    el.disabled = !!opts.disabled;
    return el;
  },
  setButtonLabel(el, text) {
    if (el.textContent !== text) el.textContent = text;
  },
  select() {
    return document.createElement("ui5-select");
  },
  fillSelect(el, items, value) {
    el.replaceChildren(
      ...items.map((item) => {
        const option = document.createElement("ui5-option");
        option.value = item.value;
        option.textContent = item.text;
        option.selected = item.value === value;
        return option;
      }),
    );
    el.value = value;
  },
  onSelectChange(el, fn) {
    el.addEventListener("change", () => fn(el.value));
  },
  input({ type, placeholder, disabled, value }) {
    const el = document.createElement("ui5-input");
    el.type = type === "number" ? "Number" : type === "email" ? "Email" : "Text";
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
    const el = document.createElement("ui5-checkbox");
    el.text = label;
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
    const card = document.createElement("ui5-card");
    const header = document.createElement("ui5-card-header");
    header.slot = "header";
    header.dataset.bootLabel = "";
    const body = document.createElement("div");
    body.className = "surface-shell-body";
    const bar = document.createElement("ui5-progress-indicator");
    body.append(bar);
    card.append(header, body);
    return card;
  },
  setBoot(el, { label, value }) {
    const heading = el.querySelector("ui5-card-header");
    const bar = el.querySelector("ui5-progress-indicator");
    if (heading && heading.titleText !== label) heading.titleText = label;
    if (bar) bar.value = value;
  },
  login() {
    const card = document.createElement("ui5-card");
    const header = document.createElement("ui5-card-header");
    header.slot = "header";
    header.dataset.loginTitle = "";
    const body = document.createElement("div");
    body.className = "surface-shell-body";
    const note = document.createElement("p");
    note.dataset.loginNote = "";
    const formHost = document.createElement("div");
    formHost.dataset.loginForm = "";
    body.append(note, formHost);
    card.append(header, body);
    return card;
  },
  setLogin(el, { title, note }) {
    const heading = el.querySelector("ui5-card-header");
    const body = el.querySelector("[data-login-note]");
    if (heading) heading.titleText = title;
    if (body) body.textContent = note;
  },
  loginFormHost(el) {
    return el.querySelector("[data-login-form]") || el;
  },
  banner() {
    const el = document.createElement("div");
    const title = document.createElement("ui5-title");
    title.level = "H5";
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
  decorateModal(dialog) {
    dialog.setAttribute("data-ui5-panel-shell", "");
  },
});

installChartPaneHost({
  legendItem({ label, swatchStyle, swatchClass }) {
    const el = document.createElement("ui5-tag");
    el.design = "Neutral";
    el.hideStateIcon = true;
    el.append(chartSwatch({ swatchStyle, swatchClass }), document.createTextNode(label));
    return el;
  },
  chartCard() {
    const el = document.createElement("ui5-card");
    const header = document.createElement("ui5-card-header");
    header.slot = "header";
    header.dataset.chartTitle = "";
    const media = document.createElement("div");
    media.dataset.chartCanvas = "";
    el.append(header, media);
    return el;
  },
  setChartCard(el, { title, hover, selected, hovered }) {
    const header = el.querySelector("[data-chart-title]");
    if (header && header.titleText !== title) header.titleText = title;
    const plain = String(hover || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    if (header && header.subtitleText !== (plain || " ")) header.subtitleText = plain || " ";
    el.classList.toggle("is-selected", !!selected);
    el.classList.toggle("is-hover", !!hovered);
  },
  chartCanvasHost(el) {
    return el.querySelector("[data-chart-canvas]");
  },
});
