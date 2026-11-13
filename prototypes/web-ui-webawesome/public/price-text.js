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
      // 本番の candle_labels は修正前の対応のまま。
      // 上に離れた日が GAP_DOWN、下に離れた日が GAP_UP なので、表示語だけ逆にする。
      ["GAP_UP", "下窓＋"],
      ["GAP_DOWN", "上窓＋"],
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
  const PLAIN_EXCLUSIVE = LIMIT_EXCLUSIVE.concat([
    ["INVALID_NAN", "判定不能"],
    ["ACTION_SUSPECT", "構造要因疑い"],
    ["SPLIT_CONFIRMED", "分割明示"],
  ]);

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function firstMatch(set, rows) {
    for (let i = 0; i < rows.length; i++) {
      if (set.has(rows[i][0])) return rows[i][1];
    }
    return "";
  }

  function toneOfText(text) {
    if (/(陽線|S高)/.test(text)) return "positive";
    if (/(陰線|S安)/.test(text)) return "negative";
    return "neutral";
  }

  function plainTag(text) {
    return '<span class="surface-price-tag" data-tone="' + toneOfText(text) + '">' + escapeHtml(text) + "</span>";
  }

  function partSpan(slot, text, tone, paint) {
    return (
      '<span class="price-part price-part-' + slot + '"' +
      (paint ? ' data-tone="' + tone + '"' : "") +
      ">" + escapeHtml(text) + "</span>"
    );
  }

  function partsHtml(labels) {
    const set = tokenSet(labels);
    if (!set) return "";
    const plain = firstExclusive(set, PLAIN_EXCLUSIVE);
    if (plain) return plainTag(plain);
    const gap = firstMatch(set, GROUPS[1]);
    const size = firstMatch(set, GROUPS[2]);
    const wick = firstMatch(set, GROUPS[3]);
    const body = firstMatch(set, GROUPS[4]);
    const dir = set.has("DOJI") ? "" : firstMatch(set, GROUPS[5]);
    const range0 = set.has("INVALID_TR0") ? "レンジ0" : "";
    const detail = range0 || (body + dir);
    if (!gap && !size && !wick && !detail && !set.has("GAP_DOMINANT")) return "";
    const gapTone = gap === "上窓＋" ? "positive" : gap === "下窓＋" ? "negative" : "neutral";
    const bodyTone = dir === "陽線" ? "positive" : dir === "陰線" ? "negative" : "neutral";
    const paintBody = bodyTone === "positive" || bodyTone === "negative";
    const title = fromLabels(labels);
    const merge = body === "丸坊主";
    const bottom = merge
      ? partSpan("d price-part-span", detail, bodyTone, paintBody || !!detail)
      : partSpan("c", wick, bodyTone, paintBody || !!wick) +
        partSpan("d", detail, bodyTone, paintBody || !!detail);
    return (
      '<span class="price-parts"' + (title ? ' title="' + escapeHtml(title) + '"' : "") + ">" +
      partSpan("a", gap, gapTone, !!gap) +
      '<span class="price-rest">' +
      partSpan("b", size, bodyTone, true) +
      '<span class="price-bottom">' +
      bottom +
      "</span></span></span>"
    );
  }

  function cellHtml(row) {
    if (!row) return "";
    if (hasCandleLabels(row)) return partsHtml(row.candle_labels);
    const text = row.price_text == null ? "" : String(row.price_text);
    return text ? plainTag(text) : "";
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
    partsHtml,
    cellHtml,
    displayText,
  };
})();
