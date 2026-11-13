const POSITIVE_HUE = "150 48% 37%";
const NEGATIVE_HUE = "6 70% 54%";
const Z_RANGE_KEYS = new Set([
  "z_turnover_60",
  "rs_acceleration_zscore",
  "rs_acceleration_zscore_topix",
  "rs_acceleration_zscore_nikkei",
  "z_disp",
]);
const PRICE_KEY = "price_text";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function parseSignedValue(text) {
  const normalized = String(text || "").trim();
  if (!normalized) return null;
  if (normalized === "±0") return 0;
  const value = Number(normalized.replace(/^\+/, ""));
  return Number.isFinite(value) ? value : null;
}

function headerLabel(header) {
  const label =
    header &&
    (header.querySelector(".th-label") ||
      header.querySelector("[data-header-label]") ||
      header.querySelector(".th-filter-btn"));
  return String(label ? label.textContent : header?.textContent || "").trim();
}

export function numberCellFormat(value, range) {
  const n = typeof value === "number" ? value : parseSignedValue(value);
  if (n == null || !Number.isFinite(n)) return null;
  const span = Number(range) > 0 ? Number(range) : 1;
  const intensity = clamp(Math.abs(n) / span, 0, 1);
  return {
    hue: n >= 0 ? POSITIVE_HUE : NEGATIVE_HUE,
    alpha: (0.02 + intensity * 0.40).toFixed(3),
  };
}

export function cfRangeForLabel(key) {
  const text = String(key || "").trim();
  if (Z_RANGE_KEYS.has(text)) return 5;
  const base = text.replace(/_(topix|nikkei)$/, "");
  return Z_RANGE_KEYS.has(base) ? 5 : 1;
}

function applyNumberFormat(cell, value, range) {
  const fmt = numberCellFormat(value, range);
  if (!fmt) return;
  cell.classList.add("surface-cf-number");
  cell.style.setProperty("--cell-hue", fmt.hue);
  cell.style.setProperty("--cell-alpha", fmt.alpha);
}

export function priceTone(text) {
  if (/(陽線|S高)/.test(text)) return "positive";
  if (/(陰線|S安)/.test(text)) return "negative";
  return "neutral";
}

function applyPriceFormat(cell) {
  if (cell.querySelector(".price-parts")) return;
  const text = String(cell.textContent || "").trim();
  if (!text) return;
  cell.classList.add("surface-cf-price");
  let tag = cell.querySelector(".surface-price-tag");
  if (!tag) {
    tag = document.createElement("span");
    tag.className = "surface-price-tag";
    tag.textContent = text;
    cell.replaceChildren(tag);
  } else if (tag.textContent !== text) {
    tag.textContent = text;
  }
  tag.dataset.tone = priceTone(text);
}

export function applyConditionalFormatting() {
  const headers = [...document.querySelectorAll("#grid thead th")];
  if (!headers.length) return;
  const keys = headers.map((header) => header.dataset.col || "");
  const priceIndex = keys.indexOf(PRICE_KEY);

  document.querySelectorAll("#grid tbody tr").forEach((row) => {
    [...row.cells].forEach((cell, index) => {
      if (cell.classList.contains("num")) {
        const rawAttr = cell.dataset.cfValue;
        const value = rawAttr != null && rawAttr !== ""
          ? Number(rawAttr)
          : parseSignedValue(cell.textContent);
        if (value != null && Number.isFinite(value)) {
          applyNumberFormat(cell, value, cfRangeForLabel(keys[index]));
        }
      }
      if (index === priceIndex) applyPriceFormat(cell);
    });
  });
}