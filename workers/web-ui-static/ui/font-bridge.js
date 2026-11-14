const proto = CanvasRenderingContext2D.prototype;
const fontProperty = Object.getOwnPropertyDescriptor(proto, "font");
const fillProperty = Object.getOwnPropertyDescriptor(proto, "fillStyle");
const productionFont = /^([\d.]+)px sans-serif$/;
const productionChartBg = /^rgb\(\s*9\s*,\s*7\s*,\s*32\s*\)$/i;

function tokenHost() {
  return document.getElementById("app-root") || document.documentElement;
}

function token(name) {
  return getComputedStyle(tokenHost()).getPropertyValue(name).trim();
}

function tokenPixels(name) {
  if (!token(name)) return null;
  const probe = document.createElement("span");
  probe.style.fontSize = `var(${name})`;
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  tokenHost().append(probe);
  const pixels = Number.parseFloat(getComputedStyle(probe).fontSize);
  probe.remove();
  return Number.isFinite(pixels) && pixels > 0 ? pixels : null;
}

Object.defineProperty(proto, "font", {
  configurable: true,
  enumerable: fontProperty.enumerable,
  get: fontProperty.get,
  set(value) {
    const match = typeof value === "string" ? productionFont.exec(value.trim()) : null;
    const family = token("--surface-font-family");
    const chartSize = tokenPixels("--surface-chart-font-size");
    if (match && family && chartSize) {
      const dpr = Number(match[1]) / 10;
      fontProperty.set.call(this, `${chartSize * dpr}px ${family}`);
      return;
    }
    fontProperty.set.call(this, value);
  },
});

Object.defineProperty(proto, "fillStyle", {
  configurable: true,
  enumerable: fillProperty.enumerable,
  get: fillProperty.get,
  set(value) {
    if (typeof value === "string" && productionChartBg.test(value.trim())) {
      const bg = token("--chart-bg");
      fillProperty.set.call(this, bg || value);
      return;
    }
    fillProperty.set.call(this, value);
  },
});