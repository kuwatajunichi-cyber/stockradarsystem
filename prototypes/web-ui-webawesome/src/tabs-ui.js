import "@awesome.me/webawesome/dist/components/tab-group/tab-group.js";

const SOURCE_ID = "kabutan-tabs-main";
const GROUP_ID = "surface-kabutan-tab-group";
const NOTE_CLASS = "surface-tab-note";

let renderQueued = false;
let sourceButtons = new Map();

function queueTabRender() {
  if (renderQueued) return;
  renderQueued = true;
  queueMicrotask(() => {
    renderQueued = false;
    renderLibraryTabs();
  });
}

function makePanelName(index) {
  return `surface-kabutan-panel-${index}`;
}

function createTab(sourceButton, panelName, active) {
  const tab = document.createElement("wa-tab");
  tab.setAttribute("panel", panelName);
  tab.textContent = sourceButton.textContent;
  tab.title = sourceButton.title;
  tab.disabled = sourceButton.disabled;
  if (active) tab.setAttribute("active", "");
  if (sourceButton.hasAttribute("data-cand")) tab.classList.add("is-candidate");
  return tab;
}

function createPanel(panelName, active) {
  const panel = document.createElement("wa-tab-panel");
  panel.setAttribute("name", panelName);
  panel.setAttribute("aria-hidden", "true");
  if (active) panel.setAttribute("active", "");
  return panel;
}

function syncMaterialNote(source, group) {
  const tabsBar = source.parentElement;
  tabsBar.querySelector(`.${NOTE_CLASS}`)?.remove();
  const sourceNote = source.querySelector(".kabutan-unknown-material");
  if (!sourceNote) return;

  const note = document.createElement("span");
  note.className = NOTE_CLASS;
  note.textContent = sourceNote.textContent;
  group.insertAdjacentElement("afterend", note);
}

function renderLibraryTabs() {
  const source = document.getElementById(SOURCE_ID);
  const group = document.getElementById(GROUP_ID);
  if (!source || !group) return;

  const buttons = [...source.querySelectorAll("button[data-kab]")];
  sourceButtons = new Map();
  const children = [];
  let activePanel = "";

  buttons.forEach((button, index) => {
    const panelName = makePanelName(index);
    const active = button.classList.contains("active");
    sourceButtons.set(panelName, button);
    children.push(createTab(button, panelName, active), createPanel(panelName, active));
    if (active) activePanel = panelName;
  });

  group.dataset.syncing = "true";
  group.replaceChildren(...children);
  group.setAttribute("active", activePanel || (buttons.length ? makePanelName(0) : ""));
  syncMaterialNote(source, group);

  Promise.resolve(group.updateComplete).then(() => {
    requestAnimationFrame(() => {
      delete group.dataset.syncing;
    });
  });
}

function installLibraryTabs() {
  const source = document.getElementById(SOURCE_ID);
  if (!source || !source.parentElement) return;

  source.hidden = true;
  source.style.display = "none";
  const group = document.createElement("wa-tab-group");
  group.id = GROUP_ID;
  group.setAttribute("activation", "auto");
  source.insertAdjacentElement("afterend", group);

  group.addEventListener("wa-tab-show", (event) => {
    if (group.dataset.syncing === "true") return;
    const sourceButton = sourceButtons.get(event.detail?.name);
    if (sourceButton && !sourceButton.disabled) sourceButton.click();
  });

  const observer = new MutationObserver(queueTabRender);
  observer.observe(source, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "disabled", "title"],
  });
  renderLibraryTabs();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", installLibraryTabs, { once: true });
} else {
  installLibraryTabs();
}
