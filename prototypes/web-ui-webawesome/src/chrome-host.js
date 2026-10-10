const SOURCE_CLASS = "surface-chrome-source";
const CHROME_ROOTS = [
  ".banner",
  ".toolbar",
  ".kabutan-tabs",
  ".kabutan-stage",
  ".modal-dialog",
  ".col-filter-menu",
  "#login-shell",
];
const SKIP_CLOSEST = "#kabutan-tabs-main, #grid, .surface-header-source, #surface-kabutan-tab-group, #fav-lists-modal, .fav-flyout, #confirm-dialog";
const LIBRARY_CONTROL = [
  "wa-select",
  "wa-button",
  "wa-input",
  "wa-checkbox",
  "wa-tag",
  "wa-card",
  "wa-progress-bar",
  "wa-dropdown",
  "wa-dropdown-item",
  "wa-dialog",
  "sp-picker",
  "sp-button",
  "sp-action-button",
  "sp-textfield",
  "sp-checkbox",
  "sp-card",
  "ui5-select",
  "ui5-button",
  "ui5-input",
  "ui5-checkbox",
  "ui5-card",
  "ui5-tag",
  "vaadin-select",
  "vaadin-button",
  "vaadin-text-field",
  "vaadin-email-field",
  "vaadin-checkbox",
  "vaadin-progress-bar",
  "lion-select",
  "lion-input",
  "lion-input-email",
  "lion-checkbox",
  "lion-button",
].join(",");

function whenReady(fn) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fn, { once: true });
  } else {
    fn();
  }
}

function markSource(el) {
  if (!el) return;
  el.classList.add(SOURCE_CLASS);
}

function alreadyWrapped(el) {
  return !el || el.dataset.surfaceWrapped === "1";
}

function markWrapped(el) {
  el.dataset.surfaceWrapped = "1";
}

function isParked(el) {
  return (
    !el ||
    el.classList.contains(SOURCE_CLASS) ||
    !!el.closest(`.${SOURCE_CLASS}`) ||
    !!el.closest(SKIP_CLOSEST)
  );
}

function isLibraryInnerControl(el) {
  if (!el) return true;
  if (el.slot === "tab" || el.slot === "input" || el.slot === "panel") return true;
  return !!el.closest(LIBRARY_CONTROL);
}

function copyLayoutClasses(source, lib) {
  for (const name of source.classList) {
    if (name === "hidden" || name === SOURCE_CLASS) continue;
    lib.classList.add(name);
  }
}

function sourceHidden(source) {
  return source.classList.contains("hidden") || source.hasAttribute("hidden");
}

function wrapButton(source, kit) {
  if (!source || alreadyWrapped(source) || isParked(source) || isLibraryInnerControl(source)) return;
  markWrapped(source);
  markSource(source);
  const lib = kit.button(source.textContent.trim(), {
    title: source.title,
    disabled: source.disabled,
    strong: source.id === "send",
    compact: !source.closest("#login-shell"),
  });
  copyLayoutClasses(source, lib);
  source.insertAdjacentElement("afterend", lib);
  lib.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    source.click();
  });
  const sync = () => {
    kit.setButtonLabel(lib, source.textContent.trim());
    if ("disabled" in lib) lib.disabled = !!source.disabled;
    if (source.title) lib.title = source.title;
    const hide = sourceHidden(source);
    lib.classList.toggle("hidden", hide);
    lib.hidden = hide;
  };
  new MutationObserver(sync).observe(source, {
    childList: true,
    characterData: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["disabled", "title", "class", "hidden", "href"],
  });
  sync();
}

function wrapSelect(source, kit) {
  if (!source || alreadyWrapped(source) || isParked(source) || isLibraryInnerControl(source)) return;
  markWrapped(source);
  markSource(source);
  const lib = kit.select(source.getAttribute("aria-label") || source.id);
  copyLayoutClasses(source, lib);
  source.insertAdjacentElement("afterend", lib);

  let lastKey = "";
  const syncFromSource = () => {
    const items = [...source.options].map((option) => ({
      value: option.value,
      text: option.textContent.trim(),
      selected: option.selected,
    }));
    const key = JSON.stringify({
      items: items.map((item) => [item.value, item.text]),
      value: source.value,
      disabled: source.disabled,
    });
    if (key === lastKey) return;
    lastKey = key;
    kit.fillSelect(lib, items, source.value);
    if ("disabled" in lib) lib.disabled = source.disabled;
  };

  kit.onSelectChange(lib, (value) => {
    if (value == null || String(source.value) === String(value)) return;
    source.value = value;
    source.dispatchEvent(new Event("change", { bubbles: true }));
  });
  source.addEventListener("change", syncFromSource);
  new MutationObserver(syncFromSource).observe(source, {
    childList: true,
    attributes: true,
    attributeFilter: ["disabled"],
  });
  syncFromSource();
}

function wrapInput(source, kit, type) {
  if (!source || alreadyWrapped(source) || isParked(source) || isLibraryInnerControl(source)) return;
  markWrapped(source);
  markSource(source);
  const relatedLabel = source.id
    ? document.querySelector(`label[for="${CSS.escape(source.id)}"]`)
    : null;
  const lib = kit.input({
    type,
    placeholder: source.placeholder || relatedLabel?.textContent.trim() || "",
    disabled: source.disabled,
    value: source.value,
    compact: !source.closest("#login-shell"),
  });
  source.insertAdjacentElement("afterend", lib);
  if (relatedLabel) {
    markSource(relatedLabel);
    relatedLabel.hidden = true;
    if ("label" in lib) lib.label = relatedLabel.textContent.trim();
    if ("placeholder" in lib) lib.placeholder = "";
  }
  kit.onInput(lib, (value) => {
    if (source.value === value) return;
    source.value = value;
    source.dispatchEvent(new Event("input", { bubbles: true }));
    source.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const sync = () => kit.setInputValue(lib, source.value);
  source.addEventListener("input", sync);
  source.addEventListener("change", sync);
}

function wrapCheckbox(source, kit) {
  if (!source || alreadyWrapped(source) || isParked(source) || isLibraryInnerControl(source)) return;
  markWrapped(source);
  const host = source.closest("label") || source;
  markSource(host);
  const labelText = String(host.textContent || "").trim();
  const lib = kit.checkbox(labelText, source.checked, source.disabled);
  host.insertAdjacentElement("afterend", lib);
  kit.onCheck(lib, (checked) => {
    if (source.checked === checked) return;
    source.checked = checked;
    source.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const sync = () => kit.setCheckbox(lib, source.checked, source.disabled);
  source.addEventListener("change", sync);
}

function wrapBoot(kit) {
  const root = document.getElementById("boot-progress");
  const card = root?.querySelector(".boot-progress-card");
  if (!root || !card || root.querySelector("[data-surface-boot]")) return;

  markSource(card);
  const overlay = kit.boot();
  overlay.setAttribute("data-surface-boot", "");
  root.append(overlay);
  kit.setBoot(overlay, {
    label: "起動オーバーレイ",
    value: 62,
  });
}

function wrapLogin(kit) {
  const shell = document.getElementById("login-shell");
  if (!shell || shell.querySelector("[data-surface-login]")) return;
  const originalCard = shell.querySelector("wa-card, sp-card, ui5-card");
  if (originalCard) markSource(originalCard);
  shell.querySelector(".banner-title") && markSource(shell.querySelector(".banner-title"));
  const title = shell.querySelector("h1");
  const note = document.getElementById("t5-login");
  if (title) markSource(title);
  if (note) markSource(note);
  const overlay = kit.login();
  overlay.setAttribute("data-surface-login", "");
  shell.insertAdjacentElement("afterbegin", overlay);
  kit.setLogin(overlay, {
    title:
      shell.querySelector(".banner-title")?.textContent.trim() ||
      title?.textContent.trim() ||
      "Stock Radar",
    note: note?.textContent.trim() || "",
  });
  if (title && !overlay.querySelector("[data-login-heading]")) {
    const heading = document.createElement("h1");
    heading.dataset.loginHeading = "";
    heading.textContent = title.textContent.trim();
    const noteEl = overlay.querySelector("[data-login-note]");
    if (noteEl) noteEl.before(heading);
    else overlay.prepend(heading);
  }
  wrapInput(document.getElementById("email"), kit, "email");
  wrapButton(document.getElementById("send"), kit);
  const email = document.getElementById("email");
  const emailLabel = document.querySelector('label[for="email"]');
  if (emailLabel) {
    markSource(emailLabel);
    emailLabel.hidden = true;
    if (email && "label" in email && !email.label) {
      email.label = emailLabel.textContent.trim() || "メール";
    }
  }
  const form = shell.querySelector("form");
  const msg = document.getElementById("msg");
  const host = kit.loginFormHost?.(overlay) || overlay;
  if (form) host.append(form);
  if (msg) host.append(msg);
}

function wrapBanner(kit) {
  const main = document.querySelector(".banner-main");
  if (!main || main.parentElement?.querySelector("[data-surface-banner]")) return;
  markSource(main);
  const overlay = kit.banner();
  overlay.setAttribute("data-surface-banner", "");
  main.insertAdjacentElement("afterend", overlay);
  const title = main.querySelector(".banner-title");
  const asof = document.getElementById("asof-banner");
  const sync = () => {
    kit.setBanner(overlay, {
      title: title?.textContent.trim() || "",
      body: asof?.textContent.trim() || "",
    });
  };
  new MutationObserver(sync).observe(main, {
    subtree: true,
    childList: true,
    characterData: true,
  });
  sync();
}

function wrapSplitter(kit) {
  const split = document.getElementById("kabutan-split");
  if (!split || split.querySelector("[data-surface-split]")) return;
  const handle = kit.splitterHandle();
  handle.setAttribute("data-surface-split", "");
  handle.classList.add("surface-split-handle");
  split.append(handle);
}

function wrapChromeControl(el, kit) {
  if (!el || alreadyWrapped(el) || isParked(el) || isLibraryInnerControl(el)) return;
  if (el.classList.contains("fav-star")) return;
  if (el.id === "boot-progress-bar") return;
  const tag = el.tagName.toLowerCase();
  if (tag === "button" || tag === "a") {
    wrapButton(el, kit);
    return;
  }
  if (tag === "select") {
    wrapSelect(el, kit);
    return;
  }
  if (el.type === "checkbox") {
    wrapCheckbox(el, kit);
    return;
  }
  if (el.matches?.("input") && el.type !== "hidden") {
    wrapInput(el, kit, el.type || "text");
  }
}

function wrapChromeControls(kit) {
  document.querySelectorAll(CHROME_ROOTS.join(",")).forEach((root) => {
    root
      .querySelectorAll(
        "button, select, input, a#kabutan-blank, a#kabutan-blocked-open, a.kabutan-open-tab, a.kabutan-blocked-btn",
      )
      .forEach((el) => wrapChromeControl(el, kit));
  });
}

function wrapModals(kit) {
  document.querySelectorAll(".modal-dialog").forEach((dialog) => {
    kit.decorateModal?.(dialog);
  });
}

export function installChromeHost(kit) {
  whenReady(() => {
    wrapBoot(kit);
    wrapLogin(kit);
    wrapBanner(kit);
    wrapSplitter(kit);
    wrapModals(kit);
    wrapChromeControls(kit);
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        wrapChromeControls(kit);
      });
    }).observe(document.body, {
      childList: true,
      subtree: true,
    });
  });
}
