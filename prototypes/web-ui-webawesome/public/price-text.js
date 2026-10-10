(() => {
  // Web UI copy from candle_labels. Edit phrases here when Web wording
  // diverges from Excel price_text. Server CSV/XLSX still use compute_price_text.
  const LIMIT_EXCLUSIVE = [
    ["LIMIT_LOW_FULL_STUCK", "S安完全張り付き疑い"],
    ["LIMIT_HIGH_FULL_STUCK", "S高完全張り付き疑い"],
    ["LIMIT_LOW_OPEN_ONLY", "S安寄底疑い"],
    ["LIMIT_HIGH_OPEN_ONLY", "S高寄天疑い"],
    ["LIMIT_LOW_TOUCH_STUCK", "S安タッチ後張付き疑い"],
    ["LIMIT_HIGH_TOUCH_STUCK", "S高タッチ後張付き疑い"],
    ["LIMIT_LOW_TOUCH", "S安タッチ疑い"],
    ["LIMIT_HIGH_TOUCH", "S高タッチ疑い"],
  ];
  const OTHER_EXCLUSIVE = [
    ["INVALID_TR0", "レンジ0"],
    ["INVALID_NAN", "判定不能"],
    ["ACTION_SUSPECT", "構造要因疑い"],
    ["SPLIT_CONFIRMED", "分割明示"],
  ];
  const GROUPS = [
    [["GAP_DOMINANT", "ギャップ主導"]],
    [
      ["GAP_UP", "上窓＋"],
      ["GAP_DOWN", "下窓＋"],
    ],
    [
      ["RANGE_VERY_LARGE", "<極大>"],
      ["RANGE_LARGE", "<大>"],
      ["RANGE_SMALL", "<小>"],
      ["RANGE_VERY_SMALL", "<極小>"],
    ],
    [
      ["WICK_BOTH_LONG", "長上下ヒゲ"],
      ["WICK_BOTH_PRESENT", "上下ヒゲ"],
      ["WICK_UPPER_LONG", "長上ヒゲ"],
      ["WICK_LOWER_LONG", "長下ヒゲ"],
      ["WICK_UPPER_PRESENT", "上ヒゲ"],
      ["WICK_LOWER_PRESENT", "下ヒゲ"],
    ],
    [
      ["DOJI", "十字線"],
      ["BODY_MARUBOZU_LIKE", "丸坊主"],
      ["BODY_LONG", "長"],
      ["BODY_SMALL", "短"],
      ["BODY_MIDDLE", "中"],
    ],
    [
      ["DIR_BULL", "陽線"],
      ["DIR_BEAR", "陰線"],
    ],
  ];
  function tokenSet(labels) {
    if (labels == null) return null;
    const raw = String(labels).trim();
    if (!raw) return null;
    return new Set(raw.split(",").map((token) => token.trim()).filter(Boolean));
  }
  function firstExclusive(set, rows) {
    let exclusive = "";
    for (let i = 0; i < rows.length; i++) {
      if (set.has(rows[i][0])) exclusive = rows[i][1];
    }
    return exclusive;
  }
  function fromLabels(labels) {
    const set = tokenSet(labels);
    if (!set) return "";
    const limit = firstExclusive(set, LIMIT_EXCLUSIVE);
    if (limit) return limit;
    const other = firstExclusive(set, OTHER_EXCLUSIVE);
    if (other) return other;
    const parts = [];
    for (let g = 0; g < GROUPS.length; g++) {
      const group = GROUPS[g];
      for (let i = 0; i < group.length; i++) {
        const token = group[i][0];
        const text = group[i][1];
        if (!set.has(token)) continue;
        if ((token === "DIR_BULL" || token === "DIR_BEAR") && set.has("DOJI")) break;
        parts.push(text);
        break;
      }
    }
    return parts.join("");
  }
  function hasCandleLabels(row) {
    return !!(row && row.candle_labels != null && String(row.candle_labels).trim());
  }
  function displayText(row) {
    if (!row) return "";
    // Production bundles include both fields. Labels always win.
    if (hasCandleLabels(row)) return fromLabels(row.candle_labels);
    return row.price_text == null ? "" : String(row.price_text);
  }
  window.StockRadarPriceText = {
    LIMIT_EXCLUSIVE,
    OTHER_EXCLUSIVE,
    GROUPS,
    hasCandleLabels,
    fromLabels,
    displayText,
  };
})();
