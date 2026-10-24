export const LIBRARIES = [
  { id: "webawesome", label: "Web Awesome" },
  { id: "spectrum", label: "Spectrum Web Components" },
  { id: "ui5", label: "UI5 Web Components" },
  { id: "vaadin", label: "Vaadin" },
  { id: "lion", label: "Lion" },
];

export function currentLibrary() {
  const requested = new URLSearchParams(window.location.search).get("lib");
  if (LIBRARIES.some((library) => library.id === requested)) return requested;

  const path = window.location.pathname.replace(/\/index\.html$/, "");
  const matched = LIBRARIES.find(
    (library) => path === `/${library.id}` || path === `/${library.id}/`,
  );
  return matched?.id || "webawesome";
}

const PAGES = {
  webawesome: "/",
  spectrum: "/spectrum/",
  ui5: "/ui5/",
  vaadin: "/vaadin/",
  lion: "/lion/",
};

export function libraryPath(id) {
  return PAGES[id] || PAGES.webawesome;
}

function previewBoot(show) {
  const root = document.getElementById("boot-progress");
  if (!root) return;
  root.classList.toggle("surface-preview", show);
  root.hidden = !show;
}

function previewLogin(show) {
  const shell = document.getElementById("login-shell");
  if (!shell) return;
  shell.classList.toggle("surface-preview", show);
  shell.hidden = !show;
}

export function installLibrarySwitcher() {
  const banner = document.querySelector(".banner");
  if (!banner || document.getElementById("library-switcher")) return;

  const current = currentLibrary();
  const cluster = document.createElement("div");
  cluster.className = "library-switcher";

  const label = document.createElement("label");
  label.htmlFor = "library-switcher";
  const caption = document.createElement("span");
  caption.textContent = "UIライブラリ";
  const select = document.createElement("select");
  select.id = "library-switcher";
  select.setAttribute("aria-label", "UIライブラリの比較");
  LIBRARIES.forEach((library) => {
    const option = document.createElement("option");
    option.value = library.id;
    option.textContent = library.label;
    option.selected = library.id === current;
    select.append(option);
  });
  select.addEventListener("change", () => {
    window.location.assign(libraryPath(select.value));
  });
  label.append(caption, select);

  const bootBtn = document.createElement("button");
  bootBtn.type = "button";
  bootBtn.id = "surface-preview-boot";
  bootBtn.textContent = "起動オーバーレイ";
  bootBtn.addEventListener("click", () => {
    const root = document.getElementById("boot-progress");
    const next = !root || root.hidden || !root.classList.contains("surface-preview");
    previewLogin(false);
    previewBoot(next);
  });

  const loginBtn = document.createElement("button");
  loginBtn.type = "button";
  loginBtn.id = "surface-preview-login";
  loginBtn.textContent = "ログインシェル";
  loginBtn.addEventListener("click", () => {
    const shell = document.getElementById("login-shell");
    const next = !shell || shell.hidden || !shell.classList.contains("surface-preview");
    previewBoot(false);
    previewLogin(next);
  });

  cluster.append(label, bootBtn, loginBtn);
  banner.append(cluster);

  const preview = new URLSearchParams(window.location.search).get("preview");
  if (preview === "boot") {
    previewLogin(false);
    previewBoot(true);
  } else if (preview === "login") {
    previewBoot(false);
    previewLogin(true);
  }
}
