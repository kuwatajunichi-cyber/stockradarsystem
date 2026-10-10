const SOURCE_CLASS = "surface-chrome-source";

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

export function chartSwatch({ swatchStyle, swatchClass }) {
  const swatch = document.createElement("i");
  swatch.setAttribute("aria-hidden", "true");
  if (swatchClass) swatch.className = swatchClass;
  if (swatchStyle) swatch.setAttribute("style", swatchStyle);
  return swatch;
}

function adoptCanvas(card, lib, kit) {
  const host = kit.chartCanvasHost?.(lib) || lib;
  const node = card.querySelector("canvas, .chart-slot");
  if (!host || !node || node.parentElement === host) return;
  host.append(node);
}

function wrapLegendItem(source, kit) {
  if (!source || alreadyWrapped(source) || !kit.legendItem) return;
  markWrapped(source);
  markSource(source);
  const swatch = source.querySelector("i");
  const lib = kit.legendItem({
    label: source.textContent.trim(),
    swatchStyle: swatch?.getAttribute("style") || "",
    swatchClass: swatch?.className || "",
  });
  lib.setAttribute("data-surface-legend", "");
  source.insertAdjacentElement("afterend", lib);
}

function wrapLegend(kit) {
  const host = document.getElementById("chart-legend");
  if (!host) return;
  [...host.children].forEach((child) => {
    if (child.tagName === "SPAN") wrapLegendItem(child, kit);
  });
}

function wrapChartCard(card, kit) {
  if (!card || alreadyWrapped(card) || !kit.chartCard) return;
  markWrapped(card);
  const heading = card.querySelector("h4");
  const hover = card.querySelector(".hover");
  if (heading) markSource(heading);
  if (hover) markSource(hover);
  const lib = kit.chartCard();
  lib.setAttribute("data-surface-chart-card", "");
  card.insertAdjacentElement("afterbegin", lib);

  const sync = () => {
    const liveHover = card.querySelector("[data-chart-hover]") || hover;
    kit.setChartCard(lib, {
      title: heading?.textContent.trim() || "",
      hover: liveHover?.innerHTML || hover?.innerHTML || "",
      selected: card.classList.contains("selected"),
      hovered: card.classList.contains("is-hover"),
    });
    adoptCanvas(card, lib, kit);
  };
  new MutationObserver(sync).observe(card, {
    childList: true,
    attributes: true,
    attributeFilter: ["class"],
  });
  if (hover) {
    new MutationObserver(sync).observe(hover, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }
  sync();
}

function wrapChartCards(kit) {
  document.querySelectorAll("#chart-host .chart-card").forEach((card) => wrapChartCard(card, kit));
}

export function installChartPaneHost(kit) {
  whenReady(() => {
    wrapLegend(kit);
    wrapChartCards(kit);
    const legend = document.getElementById("chart-legend");
    const host = document.getElementById("chart-host");
    if (legend) {
      new MutationObserver(() => wrapLegend(kit)).observe(legend, { childList: true });
    }
    if (host) {
      new MutationObserver(() => wrapChartCards(kit)).observe(host, { childList: true });
    }
  });
}
