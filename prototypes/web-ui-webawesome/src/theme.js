import "./production.css";
import "./surface-shared.css";
import "./font-bridge.js";
import {
  applyConditionalFormatting,
  cfRangeForLabel,
  numberCellFormat,
  priceTone,
} from "./conditional-format.js";
import { currentLibrary, installLibrarySwitcher } from "./library-switcher.js";

window.StockRadarChrome = {
  ...(window.StockRadarChrome || {}),
  applyConditionalFormatting,
  cfRangeForLabel,
  numberCellFormat,
  priceTone,
};

const library = currentLibrary();
document.documentElement.dataset.surfaceLibrary = library;
if (library === "webawesome") {
  document.documentElement.classList.add("wa-dark");
}
if (library === "vaadin") {
  document.documentElement.setAttribute("theme", "dark");
}
installLibrarySwitcher();

const loaders = {
  webawesome: () => import("./surfaces/webawesome.js"),
  spectrum: () => import("./surfaces/spectrum.js"),
  ui5: () => import("./surfaces/ui5.js"),
  vaadin: () => import("./surfaces/vaadin.js"),
  lion: () => import("./surfaces/lion.js"),
};

await loaders[library]();
