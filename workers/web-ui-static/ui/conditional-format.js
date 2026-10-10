const POSITIVE_HUE = "156 58% 48%";
const NEGATIVE_HUE = "346 72% 58%";
const Z_RANGE_LABELS = new Set(["Zscore", "加速Z"]);
const PRICE_LABEL = "(当日の価格挙動)";

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
  const label = header && header.querySelector(".th-label");
  return String(label ? label.textContent : header?.textContent || "").trim();
}

export function numberCellFormat(text, range) {
  const value = parseSignedValue(text);
  if (value == null) return null;
  const span = Number(range) > 0 ? Number(range) : 1;
  const intensity = clamp(Math.abs(value) / span, 0, 1);
  return {
    hue: value >= 0 ? POSITIVE_HUE : NEGATIVE_HUE,
    alpha: (0.08 + intensity * 0.2).toFixed(3),
  };
}

export function cfRangeForLabel(label) {
  return Z_RANGE_LABELS.has(String(label || "").trim()) ? 5 : 1;
}

function applyNumberFormat(cell, value, range) {
  const fmt = numberCellFormat(value === 0 ? "±0" : String(value), range);
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
  const labels = headers.map(headerLabel);
  const priceIndex = labels.indexOf(PRICE_LABEL);

  document.querySelectorAll("#grid tbody tr").forEach((row) => {
    [...row.cells].forEach((cell, index) => {
      if (cell.classList.contains("num")) {
        const value = parseSignedValue(cell.textContent);
        if (value != null) {
          applyNumberFormat(cell, value, Z_RANGE_LABELS.has(labels[index]) ? 5 : 1);
        }
      }
      if (index === priceIndex) applyPriceFormat(cell);
    });
  });
}