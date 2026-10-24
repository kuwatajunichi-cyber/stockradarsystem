const SOURCE_ID = "kabutan-tabs-main";
const GROUP_ID = "surface-kabutan-tab-group";
const NOTE_CLASS = "surface-tab-note";

export function installTabHost(adapter) {
  let renderQueued = false;
  let sourceButtons = new Map();
  let group = null;

  function queueRender() {
    if (renderQueued) return;
    renderQueued = true;
    queueMicrotask(() => {
      renderQueued = false;
      render();
    });
  }

  function syncMaterialNote(source) {
    const tabsBar = source.parentElement;
    tabsBar?.querySelector(`.${NOTE_CLASS}`)?.remove();
    const sourceNote = source.querySelector(".kabutan-unknown-material");
    if (!sourceNote || !group) return;

    const note = document.createElement("span");
    note.className = NOTE_CLASS;
    note.textContent = sourceNote.textContent;
    group.insertAdjacentElement("afterend", note);
  }

  function render() {
    const source = document.getElementById(SOURCE_ID);
    if (!source || !group) return;

    const buttons = [...source.querySelectorAll("button[data-kab]")];
    sourceButtons = new Map();
    group.dataset.syncing = "true";
    adapter.sync(group, buttons, sourceButtons);
    syncMaterialNote(source);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        delete group.dataset.syncing;
      });
    });
  }

  function activate(button) {
    if (!button || button.disabled || button.classList.contains("active")) return;
    if (group?.dataset.syncing === "true") return;
    button.click();
  }

  function install() {
    const source = document.getElementById(SOURCE_ID);
    if (!source?.parentElement || document.getElementById(GROUP_ID)) return;

    source.hidden = true;
    source.style.display = "none";
    group = adapter.createGroup();
    group.id = GROUP_ID;
    source.insertAdjacentElement("afterend", group);
    adapter.bind(group, () => sourceButtons, activate);

    const observer = new MutationObserver(queueRender);
    observer.observe(source, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "disabled", "title"],
    });
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
}
