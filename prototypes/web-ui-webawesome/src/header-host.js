const SOURCE_CLASS = "surface-header-source";
const CELL_ATTR = "data-surface-header";

export function installHeaderHost(adapter) {
  const observer = new MutationObserver(queueRender);
  let renderQueued = false;

  function queueRender() {
    if (renderQueued) return;
    renderQueued = true;
    queueMicrotask(() => {
      renderQueued = false;
      render();
    });
  }

  function describe(th) {
    const labelNode = th.querySelector(".th-label");
    const source = th.querySelector(`.${SOURCE_CLASS}`);
    const mark = th.querySelector(".th-sort-mark");
    const filterBtn = th.querySelector(".th-filter-btn");
    const label = String(
      labelNode?.textContent || source?.textContent || "",
    ).trim();
    const sortMark = String(mark?.textContent || "").trim();
    return {
      label,
      caption: sortMark ? `${label} ${sortMark}` : label,
      title: filterBtn?.title || label,
      numeric: th.classList.contains("th-numeric"),
      filterable: th.classList.contains("th-filterable") || !!th.querySelector(".th-filter-btn"),
      sorted: th.classList.contains("th-sorted"),
      filtered: th.classList.contains("th-filtered"),
      sortMark,
      sortDirection: sortMark === "↑" ? "asc" : sortMark === "↓" ? "desc" : "",
    };
  }

  function wrap(th) {
    if (th.querySelector(`.${SOURCE_CLASS}`)) return;
    const source = document.createElement("span");
    source.className = SOURCE_CLASS;
    while (th.firstChild) source.appendChild(th.firstChild);
    th.append(source);
  }

  function activate(th) {
    th.querySelector(".th-filter-btn")?.click();
  }

  function render() {
    const grid = document.getElementById("grid");
    const thead = grid?.tHead;
    if (!grid || !thead) {
      observe(document.body);
      return;
    }

    observer.disconnect();
    [...thead.querySelectorAll("th")].forEach((th) => {
      wrap(th);
      const meta = describe(th);
      let cell = th.querySelector(`[${CELL_ATTR}]`);
      if (!cell) {
        cell = adapter.create(meta);
        cell.setAttribute(CELL_ATTR, "");
        cell.addEventListener(
          "click",
          (event) => {
            event.preventDefault();
            event.stopPropagation();
            activate(th);
          },
          true,
        );
        adapter.bind?.(cell, () => activate(th));
        th.append(cell);
      }
      cell.classList.toggle("is-sorted", meta.sorted);
      cell.classList.toggle("is-filtered", meta.filtered);
      cell.classList.toggle("is-numeric", meta.numeric);
      adapter.sync(cell, meta);
    });
    observe(grid);
  }

  function observe(target) {
    observer.observe(target, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  function install() {
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
}
