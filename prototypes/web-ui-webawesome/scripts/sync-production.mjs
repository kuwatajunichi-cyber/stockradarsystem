import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const prototypeRoot = resolve(here, "..");
const repositoryRoot = resolve(here, "..", "..", "..");
const productionAssets = resolve(repositoryRoot, "workers", "web-ui-static", "assets");

const productionHtmlPath = resolve(productionAssets, "index.html");
const productionAppPath = resolve(productionAssets, "app.js");
const productionPriceTextPath = resolve(productionAssets, "price-text.js");
const productionCssPath = resolve(productionAssets, "styles.css");
const generatedAppPath = resolve(prototypeRoot, "public", "production-app.js");
const generatedPriceTextPath = resolve(prototypeRoot, "public", "price-text.js");
const generatedCssPath = resolve(prototypeRoot, "src", "production.css");
const generatedHtmlPath = resolve(prototypeRoot, "index.html");

mkdirSync(dirname(generatedAppPath), { recursive: true });
mkdirSync(dirname(generatedCssPath), { recursive: true });

copyFileSync(productionAppPath, generatedAppPath);
copyFileSync(productionPriceTextPath, generatedPriceTextPath);
copyFileSync(productionCssPath, generatedCssPath);

const stylesheetTag = '<link rel="stylesheet" href="/styles.css" />';
const productionScripts =
  '  <script src="/price-text.js"></script>\n' +
  '  <script src="/app.js"></script>\n  <script type="module" src="/live.js"></script>';
const prototypeScripts =
  '  <script src="/price-text.js"></script>\n' +
  '  <script src="/production-app.js"></script>\n' +
  '  <script type="module" src="/src/mock-live.js"></script>';

let html = readFileSync(productionHtmlPath, "utf8");
if (!html.includes(stylesheetTag)) {
  throw new Error("production stylesheet tag changed; update sync-production.mjs");
}
if (!html.includes(productionScripts)) {
  throw new Error("production script tags changed; update sync-production.mjs");
}

html = html
  .replace(stylesheetTag, '<script type="module" src="/src/theme.js"></script>')
  .replace(productionScripts, prototypeScripts);

writeFileSync(
  generatedHtmlPath,
  `<!-- Generated from workers/web-ui-static/assets/index.html. Do not hand-edit. -->\n${html}`,
  "utf8",
);

console.log("Synchronized production index.html, app.js, price-text.js, and styles.css");
