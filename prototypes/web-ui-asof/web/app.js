(() => {
  const XLSX_DEFAULT = [
    { key: "code", label: "コード", kind: "text" },
    { key: "name", label: "銘柄名", kind: "text" },
    { key: "favorite", label: "お気入り", kind: "favorite" },
    { key: "link_kabutan", label: "概要", kind: "link", linkText: "株探" },
    { key: "link_kabutan_chart", label: "チャート", kind: "link", linkText: "チャート" },
    { key: "link_kabutan_news", label: "ニュース", kind: "link", linkText: "ニュース" },
    { key: "price_text", label: "(当日の価格挙動)", kind: "text" },
    { key: "z_turnover_60", label: "Zscore", kind: "signed1" },
    { key: "rs_acceleration_zscore_topix", label: "加速Z", kind: "signed1", bench: true },
    { key: "rs_acceleration_topix", label: "加速", kind: "signed1", bench: true },
    { key: "rs31_topix", label: "31日", kind: "signed1", bench: true },
    { key: "rs63_topix", label: "63日", kind: "signed1", bench: true },
    { key: "rs126_topix", label: "126日", kind: "signed1", bench: true },
    { key: "rs252_topix", label: "252日", kind: "signed1", bench: true },
    { key: "rs_sma75_topix", label: "SMA75 RS", kind: "signed1", bench: true },
    { key: "event_news_bundle", label: "売買代金急増 要因ニュース候補", kind: "news_bundle" },
    { key: "research_prompt_block", label: "調査ブロック", kind: "text" },
  ];

  // Draw order = array order (back → front). Z bars first; RS lines by thickness.
  const CHART_BG = "rgb(9,7,32)";
  const RS_POS = "39,255,104";
  const RS_NEG = "255,39,115";
  const SERIES_META = [
    { id: "z_disp", label: "Zscore", kind: "bar", color: "rgba(196,192,242,0.34)" },
    { id: "rs_sma75", label: "SMA75RS", kind: "line", width: 16, alpha: 0.1 },
    { id: "rs252", label: "RS252", kind: "line", width: 8, alpha: 0.2 },
    { id: "rs126", label: "RS126", kind: "line", width: 6, alpha: 0.4 },
    { id: "rs63", label: "RS63", kind: "line", width: 4, alpha: 0.6 },
    { id: "rs31", label: "RS31", kind: "line", width: 1, alpha: 1.0 },
  ];

  const state = {
    meta: null,
    rows: [],
    allKeys: [],
    visibleKeys: XLSX_DEFAULT.map((c) => c.key).filter((k) =>
      !["link_kabutan", "link_kabutan_chart", "link_kabutan_news"].includes(k)
    ),
    colDefs: Object.fromEntries(XLSX_DEFAULT.map((c) => [c.key, c])),
    asOf: null,
    availableDates: [],
    bench: "topix",
    freePreview: false,
    userId: "local",
    favorites: {},
    favOnly: false,
    excludeAllRsNeg: false,
    sortKey: "z_turnover_60",
    sortDir: "desc",
    colFilters: {},
    filterMenuKey: null,
    tabSettings: null,
    selected: null,
    hovered: null,
    seriesCache: {},
    visibleChartCodes: [],
    chartBuildId: 0,
    chartObserver: null,
    kabutanMode: "overview",
    kabutanTimer: null,
    rowObserver: null,
  };

  const $ = (id) => document.getElementById(id);


  const LINK_KEYS_OPTIONAL = new Set(["link_kabutan", "link_kabutan_chart", "link_kabutan_news"]);
  const HIDDEN_COL_KEYS = new Set([
    "date",
    "event_news_1_title",
    "event_news_2_title",
    "event_news_3_title",
    "event_news_1_url",
    "event_news_2_url",
    "event_news_3_url",
    "event_news_1_source",
    "event_news_2_source",
    "event_news_3_source",
    "event_news_1_score",
    "event_news_2_score",
    "event_news_3_score",
  ]);


  const EXTRA_COL_DEFS = {
    beta_adjusted_rs_topix: { key: "beta_adjusted_rs_topix", label: "β調整RS", kind: "signed1", bench: true },
    information_ratio_topix: { key: "information_ratio_topix", label: "情報比率", kind: "signed1", bench: true },
    perfect_order_days: { key: "perfect_order_days", label: "パーフェクトオーダー日数", kind: "int" },
    price_change_pct: { key: "price_change_pct", label: "騰落率(%)", kind: "signed1" },
    turnover_ma_ratio_60: { key: "turnover_ma_ratio_60", label: "売買代金MA比", kind: "signed1" },
  };

  const COLS_PANEL_OMIT_KEYS = new Set([
    "candle_labels",
    "event_cause_type",
    "n_bars_used",
    "turnover_yen",
  ]);

  function omitFromColsPanel(k) {
    if (!k || HIDDEN_COL_KEYS.has(k)) return true;
    if (k === "date") return true;
    if (COLS_PANEL_OMIT_KEYS.has(k)) return true;
    // WEB links and companion title/meta fields
    if (k.startsWith("link_")) return true;
    if (/^event_news_[123]_/.test(k)) return true;
    // bench variations: UI uses bench toggle on *_topix keys; hide *_nikkei twins
    if (k.endsWith("_nikkei")) return true;
    return false;
  }

  function ensureColDefs() {
    state.colDefs = {
      ...Object.fromEntries(XLSX_DEFAULT.map((c) => [c.key, c])),
      ...EXTRA_COL_DEFS,
    };
  }



  const CF_PM5 = new Set([
    "z_turnover_60",
    "rs_acceleration_zscore_topix",
  ]);
  const CF_PM1 = new Set([
    "rs_acceleration_topix",
    "rs31_topix",
    "rs63_topix",
    "rs126_topix",
    "rs252_topix",
    "rs_sma75_topix",
  ]);
  const CF_LO = [0xe6, 0x7c, 0x73];
  const CF_MID = [0xff, 0xff, 0xff];
  const CF_HI = [0x57, 0xbb, 0x8a];
  const PRICE_TEXT_CF = [
    { needle: "陽線", bg: "#B8DBC6", fg: null },
    { needle: "陰線", bg: "#E7C0BA", fg: null },
    { needle: "S高", bg: "#006342", fg: "#FFFFFF" },
    { needle: "S安", bg: "#AD2800", fg: "#FFFFFF" },
    { needle: "構造要因疑い", bg: "#69697F", fg: "#FFFFFF" },
    { needle: "レンジ0", bg: "#69697F", fg: "#FFFFFF" },
  ];


  function favStorageKey(userId) {
    return "web_ui_asof_favorites_v1:" + String(userId || "local");
  }

  function loadFavorites(userId) {
    try {
      const raw = localStorage.getItem(favStorageKey(userId));
      if (!raw) return {};
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return {};
      const out = {};
      arr.forEach((c) => {
        const code = String(c).padStart(4, "0");
        out[code] = true;
      });
      return out;
    } catch (_) {
      return {};
    }
  }

  function saveFavorites() {
    const codes = Object.keys(state.favorites).filter((c) => state.favorites[c]).sort();
    localStorage.setItem(favStorageKey(state.userId), JSON.stringify(codes));
  }

  function isFavorite(code) {
    return !!state.favorites[String(code).padStart(4, "0")];
  }

  function toggleFavorite(code) {
    if (state.freePreview) return;
    const c = String(code).padStart(4, "0");
    if (state.favorites[c]) delete state.favorites[c];
    else state.favorites[c] = true;
    saveFavorites();
    renderTable();
  }

  function setFavoritesUiEnabled(enabled) {
    const userLab = $("fav-user-label");
    const user = $("fav-user");
    if (user) user.disabled = !enabled;
    if (userLab) userLab.classList.toggle("disabled-fav", !enabled);
    document.body.classList.toggle("fav-disabled", !enabled);
  }


  const RS_FILTER_KEYS = [
    "rs31_topix",
    "rs63_topix",
    "rs126_topix",
    "rs252_topix",
    "rs_sma75_topix",
  ];


  function isNumericCol(key) {
    const def = state.colDefs[key];
    return !!(def && (def.kind === "signed1" || def.kind === "int"));
  }

  function colFilterActive(key) {
    const f = state.colFilters[key];
    return !!(f && f.op && f.op !== "none");
  }

  function parseFilterNum(v) {
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  }

  function rowPassesColFilter(row, baseKey, filt) {
    if (!filt || !filt.op || filt.op === "none") return true;
    const key = mapKey(baseKey);
    const raw = row[key];
    const isNull = raw == null || Number.isNaN(Number(raw));
    if (filt.op === "isnull") return isNull;
    if (filt.op === "notnull") return !isNull;
    if (isNull) return false;
    const n = Number(raw);
    const a = filt.a;
    const b = filt.b;
    if (filt.op === "eq") return a != null && n === a;
    if (filt.op === "gt") return a != null && n > a;
    if (filt.op === "gte") return a != null && n >= a;
    if (filt.op === "lt") return a != null && n < a;
    if (filt.op === "lte") return a != null && n <= a;
    if (filt.op === "between") {
      if (a == null || b == null) return true;
      const lo = Math.min(a, b);
      const hi = Math.max(a, b);
      return n >= lo && n <= hi;
    }
    return true;
  }

  function applyColFilters(rows) {
    const entries = Object.entries(state.colFilters || {}).filter(([, f]) => f && f.op && f.op !== "none");
    if (!entries.length) return rows;
    return rows.filter((row) => entries.every(([k, f]) => rowPassesColFilter(row, k, f)));
  }

  function closeFilterMenu() {
    state.filterMenuKey = null;
    document.querySelectorAll(".col-filter-menu").forEach((el) => el.remove());
  }

  function setSort(key, dir) {
    if (state.freePreview) return;
    state.sortKey = key;
    state.sortDir = dir;
    closeFilterMenu();
    state.visibleChartCodes = [];
    $("chart-host").innerHTML = "";
    renderTable();
  }

  function clearSort() {
    if (state.freePreview) return;
    state.sortKey = null;
    state.sortDir = "desc";
    closeFilterMenu();
    state.visibleChartCodes = [];
    $("chart-host").innerHTML = "";
    renderTable();
  }

  function applyColFilterFromMenu(key) {
    if (state.freePreview) return;
    const opEl = document.getElementById("cfm-op");
    const aEl = document.getElementById("cfm-a");
    const bEl = document.getElementById("cfm-b");
    if (!opEl) return;
    const op = opEl.value;
    const a = parseFilterNum(aEl ? aEl.value : "");
    const b = parseFilterNum(bEl ? bEl.value : "");
    if (op === "none") delete state.colFilters[key];
    else state.colFilters[key] = { op, a, b };
    closeFilterMenu();
    state.visibleChartCodes = [];
    $("chart-host").innerHTML = "";
    renderTable();
  }

  function clearColFilter(key) {
    if (state.freePreview) return;
    delete state.colFilters[key];
    closeFilterMenu();
    state.visibleChartCodes = [];
    $("chart-host").innerHTML = "";
    renderTable();
  }

  function openFavFilterMenu(th) {
    closeFilterMenu();
    state.filterMenuKey = "favorite";
    const locked = !!state.freePreview;
    const menu = document.createElement("div");
    menu.className = "col-filter-menu" + (locked ? " is-locked" : "");
    menu.addEventListener("click", (ev) => ev.stopPropagation());

    if (locked) {
      const note = document.createElement("p");
      note.className = "cfm-note muted";
      note.textContent = "無料プレビュー中はお気入りフィルタを変更できません。";
      menu.appendChild(note);
    }

    const sec = document.createElement("div");
    sec.className = "cfm-section";
    const lab = document.createElement("label");
    lab.className = "cfm-check";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!state.favOnly && !locked;
    cb.disabled = locked;
    cb.addEventListener("change", () => {
      if (locked) {
        cb.checked = false;
        return;
      }
      state.favOnly = cb.checked;
      closeFilterMenu();
      state.visibleChartCodes = [];
      $("chart-host").innerHTML = "";
      renderTable();
    });
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(" お気入りのみ表示"));
    sec.appendChild(lab);
    menu.appendChild(sec);

    document.body.appendChild(menu);
    const rect = th.getBoundingClientRect();
    const mw = Math.max(220, menu.offsetWidth);
    let left = rect.left;
    if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8);
    menu.style.left = left + "px";
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8) + "px";
  }

  function openFilterMenu(th, key) {
    closeFilterMenu();
    if (!isNumericCol(key)) return;
    state.filterMenuKey = key;
    const locked = !!state.freePreview;
    const menu = document.createElement("div");
    menu.className = "col-filter-menu" + (locked ? " is-locked" : "");
    menu.addEventListener("click", (ev) => ev.stopPropagation());

    const cur = state.colFilters[key] || { op: "none", a: null, b: null };
    const sortedHere = state.sortKey === key;

    if (locked) {
      const note = document.createElement("p");
      note.className = "cfm-note muted";
      note.textContent = "無料プレビュー中はソート/フィルタを変更できません。";
      menu.appendChild(note);
    }

    const secSort = document.createElement("div");
    secSort.className = "cfm-section";
    function addSortBtn(dir, label) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.disabled = locked;
      if (sortedHere && state.sortDir === dir) b.classList.add("active");
      b.addEventListener("click", () => {
        if (locked) return;
        setSort(key, dir);
      });
      secSort.appendChild(b);
    }
    addSortBtn("desc", "↓ 降順でソート");
    addSortBtn("asc", "↑ 昇順でソート");
    if (sortedHere) {
      const clr = document.createElement("button");
      clr.type = "button";
      clr.textContent = "ソート解除";
      clr.disabled = locked;
      clr.addEventListener("click", () => {
        if (locked) return;
        clearSort();
      });
      secSort.appendChild(clr);
    }
    menu.appendChild(secSort);

    const secFilt = document.createElement("div");
    secFilt.className = "cfm-section";
    const lab = document.createElement("label");
    lab.appendChild(document.createTextNode("フィルタ"));
    const sel = document.createElement("select");
    sel.id = "cfm-op";
    sel.disabled = locked;
    [
      ["none", "（なし）"],
      ["gt", "＞ より大きい"],
      ["gte", "≥ 以上"],
      ["lt", "＜ より小さい"],
      ["lte", "≤ 以下"],
      ["eq", "＝ 等しい"],
      ["between", "範囲（以下〜以上）"],
      ["notnull", "空白でない"],
      ["isnull", "空白"],
    ].forEach(([v, t]) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = t;
      sel.appendChild(o);
    });
    sel.value = cur.op || "none";
    lab.appendChild(sel);
    secFilt.appendChild(lab);

    const vals = document.createElement("div");
    vals.className = "cfm-vals";
    const aEl = document.createElement("input");
    aEl.id = "cfm-a";
    aEl.type = "number";
    aEl.step = "any";
    aEl.placeholder = "値";
    aEl.disabled = locked;
    if (cur.a != null) aEl.value = String(cur.a);
    const bEl = document.createElement("input");
    bEl.id = "cfm-b";
    bEl.type = "number";
    bEl.step = "any";
    bEl.placeholder = "上限";
    bEl.disabled = locked;
    if (cur.b != null) bEl.value = String(cur.b);
    vals.appendChild(aEl);
    vals.appendChild(bEl);
    secFilt.appendChild(vals);

    function syncValVisibility() {
      const needA = ["gt", "gte", "lt", "lte", "eq", "between"].includes(sel.value);
      const needB = sel.value === "between";
      aEl.classList.toggle("hidden", !needA);
      bEl.classList.toggle("hidden", !needB);
    }
    syncValVisibility();
    sel.addEventListener("change", syncValVisibility);

    const actions = document.createElement("div");
    actions.className = "cfm-actions";
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.textContent = "適用";
    applyBtn.disabled = locked;
    applyBtn.addEventListener("click", () => {
      if (locked) return;
      applyColFilterFromMenu(key);
    });
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.textContent = "フィルタ清除";
    clearBtn.disabled = locked;
    clearBtn.addEventListener("click", () => {
      if (locked) return;
      clearColFilter(key);
    });
    actions.appendChild(applyBtn);
    actions.appendChild(clearBtn);
    secFilt.appendChild(actions);
    menu.appendChild(secFilt);

    document.body.appendChild(menu);
    const rect = th.getBoundingClientRect();
    const mw = Math.max(240, menu.offsetWidth);
    let left = rect.left;
    if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8);
    menu.style.left = left + "px";
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8) + "px";
  }

  function isAllRsNegative(row) {
    let saw = 0;
    for (const base of RS_FILTER_KEYS) {
      const v = row[mapKey(base)];
      if (v == null || Number.isNaN(Number(v))) return false;
      saw += 1;
      if (!(Number(v) < 0)) return false;
    }
    return saw === RS_FILTER_KEYS.length;
  }

  function openFilterModal() {
    syncFilterModalUi();
    const modal = $("filter-modal");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeFilterModal() {
    const modal = $("filter-modal");
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  function syncFilterModalUi() {
    const sw = $("filter-exclude-all-rs-neg");
    const lab = $("filter-exclude-all-rs-neg-label");
    if (sw) {
      sw.checked = !!state.excludeAllRsNeg && !state.freePreview;
      sw.disabled = !!state.freePreview;
    }
    if (lab) lab.classList.toggle("disabled-filter", !!state.freePreview);
    const note = $("filter-modal-note");
    if (note) {
      note.textContent = state.freePreview
        ? "無料プレビュー中は特殊フィルタを変更できません。"
        : "";
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function safeHttpUrl(v) {
    const raw = String(v || "").trim();
    if (!raw) return "";
    try {
      const u = new URL(raw);
      if (u.protocol !== "http:" && u.protocol !== "https:") return "";
      return u.href;
    } catch {
      return "";
    }
  }

  function clamp01(t) {
    return Math.max(0, Math.min(1, t));
  }

  function lerpRgb(a, b, t) {
    const u = clamp01(t);
    return (
      "rgb(" +
      [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * u)).join(",") +
      ")"
    );
  }

  function colorScaleBg(v, absEnd) {
    if (v == null || Number.isNaN(Number(v))) return null;
    const n = Number(v);
    if (n <= 0) return lerpRgb(CF_LO, CF_MID, (n - -absEnd) / absEnd);
    return lerpRgb(CF_MID, CF_HI, n / absEnd);
  }

  function priceTextCf(text) {
    if (text == null || text === "") return null;
    const s = String(text);
    for (const rule of PRICE_TEXT_CF) {
      if (s.includes(rule.needle)) return rule;
    }
    return null;
  }


  const UNKNOWN_MATERIAL_TEXT = "\u6750\u6599\u4e0d\u660e\u30fb\u9700\u7d66\u8d77\u56e0\u7591\u3044";

  function isUnknownMaterialRow(row) {
    const items = eventNewsItems(row);
    if (!items.length) return false;
    if (String(items[0].title).trim() !== UNKNOWN_MATERIAL_TEXT) return false;
    return items.slice(1).every((it) => !String(it.title || "").trim());
  }

  function eventNewsItems(row) {
    if (!row) return [];
    const bundled = row.event_news_bundle;
    if (Array.isArray(bundled) && bundled.length) {
      const fromBundle = [];
      for (let i = 0; i < bundled.length && i < 3; i++) {
        const it = bundled[i] || {};
        const title = it.title;
        if (title == null || String(title).trim() === "") continue;
        fromBundle.push({
          n: fromBundle.length + 1,
          title: String(title),
          url: it.url || null,
        });
      }
      if (fromBundle.length) return fromBundle;
    }
    const items = [];
    for (let i = 1; i <= 3; i++) {
      const title = row["event_news_" + i + "_title"];
      if (title == null || String(title).trim() === "") continue;
      items.push({
        n: i,
        title: String(title),
        url: row["event_news_" + i + "_url"] || null,
      });
    }
    return items;
  }

  function tabLabel10(title) {
    const s = String(title);
    return s.length <= 10 ? s : s.slice(0, 10);
  }

  function cellStyle(row, baseKey) {
    if (baseKey === "price_text") {
      const rule = priceTextCf(row.price_text);
      if (!rule) return null;
      return { bg: rule.bg, fg: rule.fg };
    }
    const mapped = mapKey(baseKey);
    // CF keys are stored as topix base keys in CF_* sets
    if (CF_PM5.has(baseKey)) {
      const bg = colorScaleBg(row[mapped], 5);
      return bg ? { bg, fg: "#111111" } : null;
    }
    if (CF_PM1.has(baseKey)) {
      const bg = colorScaleBg(row[mapped], 1);
      return bg ? { bg, fg: "#111111" } : null;
    }
    return null;
  }


  function mapKey(key) {
    if (state.bench === "topix") return key;
    return key.replaceAll("_topix", "_nikkei");
  }

  function fmtSigned1(v) {
    if (v == null || Number.isNaN(Number(v))) return "";
    const n = Number(v);
    if (Object.is(n, 0) || Math.abs(n) < 5e-5) return "±0";
    return (n >= 0 ? "+" : "") + n.toFixed(1);
  }

  function freePreviewKeep(zs, topN = 20) {
    const indexed = [];
    for (let i = 0; i < zs.length; i++) {
      const z = zs[i];
      if (z == null || Number.isNaN(Number(z))) continue;
      indexed.push([i, Number(z)]);
    }
    indexed.sort((a, b) => (b[1] - a[1]) || (a[0] - b[0]));
    const keep = Array(zs.length).fill(false);
    if (!indexed.length) return keep;
    if (indexed.length <= topN) {
      indexed.forEach(([i]) => { keep[i] = true; });
      return keep;
    }
    const thr = indexed[topN - 1][1];
    for (const [i, z] of indexed) {
      if (z >= thr) keep[i] = true;
      else break;
    }
    return keep;
  }

  function displayRows() {
    let rows = state.rows.slice();
    if (state.freePreview) {
      const mask = freePreviewKeep(rows.map((r) => r.z_turnover_60));
      rows = rows.filter((_, i) => mask[i]);
    } else {
      if (state.favOnly) {
        rows = rows.filter((r) => isFavorite(r.code));
      }
      if (state.excludeAllRsNeg) {
        rows = rows.filter((r) => !isAllRsNegative(r));
      }
    }
    if (!state.freePreview) {
      rows = applyColFilters(rows);
    }
    const sortKey = state.freePreview
      ? "z_turnover_60"
      : (state.sortKey ? mapKey(state.sortKey) : null);
    const dir = state.freePreview ? "desc" : state.sortDir;
    if (sortKey) {
      rows.sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey];
        const aNull = av == null || Number.isNaN(Number(av));
        const bNull = bv == null || Number.isNaN(Number(bv));
        if (aNull && bNull) return String(a.code).localeCompare(String(b.code));
        if (aNull) return 1;
        if (bNull) return -1;
        const an = Number(av), bn = Number(bv);
        if (!Number.isNaN(an) && !Number.isNaN(bn)) return dir === "desc" ? bn - an : an - bn;
        return dir === "desc" ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
      });
    }
    return rows;
  }



  function initKabutanSplitter() {
    const left = $("main-left");
    const split = $("kabutan-split");
    if (!left || !split) return;
    if (split.dataset.bound === "1") return;
    split.dataset.bound = "1";

    const KEY = "web_ui_asof_kabutan_h";
    const saved = localStorage.getItem(KEY);
    if (saved) left.style.setProperty("--kabutan-h", saved);

    let dragging = false;

    function setKabutanHeight(clientY) {
      const rect = left.getBoundingClientRect();
      const splitH = split.getBoundingClientRect().height || 6;
      const minTable = 80;
      const minKab = 120;
      let kabH = rect.bottom - clientY;
      const maxKab = Math.max(minKab, rect.height - minTable - splitH);
      kabH = Math.max(minKab, Math.min(maxKab, kabH));
      const px = Math.round(kabH) + "px";
      left.style.setProperty("--kabutan-h", px);
      return px;
    }

    function onMove(ev) {
      if (!dragging) return;
      ev.preventDefault();
      const y = ev.touches ? ev.touches[0].clientY : ev.clientY;
      setKabutanHeight(y);
    }

    function onUp() {
      if (!dragging) return;
      dragging = false;
      split.classList.remove("dragging");
      document.body.classList.remove("is-row-resizing");
      const frame = $("kabutan-frame");
      if (frame) frame.style.pointerEvents = "";
      const val = getComputedStyle(left).getPropertyValue("--kabutan-h").trim();
      if (val) localStorage.setItem(KEY, val);
    }

    split.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      dragging = true;
      split.classList.add("dragging");
      document.body.classList.add("is-row-resizing");
      const frame = $("kabutan-frame");
      if (frame) frame.style.pointerEvents = "none";
      try { split.setPointerCapture(ev.pointerId); } catch (_) {}
      setKabutanHeight(ev.clientY);
    });
    split.addEventListener("pointermove", onMove);
    split.addEventListener("pointerup", onUp);
    split.addEventListener("pointercancel", onUp);
    window.addEventListener("pointerup", onUp);
  }


  function openColsModal() {
    renderColsPanel();
    const modal = $("cols-modal");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeColsModal() {
    const modal = $("cols-modal");
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  function renderColsPanel() {
    const panel = $("cols-panel");
    panel.innerHTML = "";
    const keys = [...new Set([...XLSX_DEFAULT.map((c) => c.key), ...state.allKeys])]
      .filter((k) => !omitFromColsPanel(k));
    keys.forEach((k) => {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.visibleKeys.includes(k);
      cb.addEventListener("change", () => {
        if (cb.checked) {
          if (!state.visibleKeys.includes(k)) state.visibleKeys.push(k);
        } else {
          state.visibleKeys = state.visibleKeys.filter((x) => x !== k);
        }
        renderTable();
      });
      const def = state.colDefs[k];
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + (def ? def.label : k)));
      panel.appendChild(lab);
    });
  }

  function renderLegend() {
    const host = $("chart-legend");
    host.innerHTML = "";
    SERIES_META.forEach((s) => {
      const el = document.createElement("span");
      if (s.kind === "bar") {
        el.innerHTML = '<i style="background:' + s.color + ';height:10px"></i>' + s.label;
      } else {
        const a = s.alpha;
        el.innerHTML =
          '<i class="rs-swatch" style="' +
          "background:linear-gradient(90deg,rgba(" + RS_NEG + "," + a + ") 50%,rgba(" + RS_POS + "," + a + ") 50%);" +
          "height:" + Math.max(2, Math.min(10, s.width / 2)) + "px" +
          '"></i>' + s.label;
      }
      host.appendChild(el);
    });
  }

  function cellHtml(row, baseKey) {
    const key = mapKey(baseKey);
    const def = state.colDefs[baseKey] || { kind: "text" };
    if (def.kind === "favorite") {
      const code = String(row.code).padStart(4, "0");
      const on = isFavorite(code);
      const disabled = state.freePreview ? " disabled" : "";
      const cls = "fav-star" + (on ? " on" : "") + (state.freePreview ? " disabled" : "");
      const label = on ? "★" : "☆";
      return (
        '<button type="button" class="' +
        cls +
        '" data-fav-code="' +
        code +
        '" aria-pressed="' +
        (on ? "true" : "false") +
        '" aria-label="favorite"' +
        disabled +
        ">" +
        label +
        "</button>"
      );
    }
    if (def.kind === "news_bundle") {
      const items = eventNewsItems(row);
      if (!items.length) return "";
      return items
        .map((it) => {
          const t = escapeHtml(it.title);
          const href = safeHttpUrl(it.url);
          if (href) {
            return (
              '<div class="news-line"><a href="' +
              escapeHtml(href) +
              '" target="_blank" rel="noopener">' +
              t +
              "</a></div>"
            );
          }
          return '<div class="news-line">' + t + "</div>";
        })
        .join("");
    }
    const v = row[key];
    if (def.kind === "link") {
      const href = safeHttpUrl(v);
      if (!href) return "";
      const t = def.linkText || "開く";
      return '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener">' + escapeHtml(t) + "</a>";
    }
    if (def.kind === "signed1") return escapeHtml(fmtSigned1(v));
    if (def.kind === "int") {
      if (v == null || Number.isNaN(Number(v))) return "";
      return escapeHtml(String(Math.round(Number(v))));
    }
    return v == null ? "" : escapeHtml(String(v));
  }

  function renderTable() {
    const rows = displayRows();
    $("row-count").textContent = "表示 " + rows.length + " / 全 " + state.rows.length + " 銘柄";
    const thead = document.querySelector("#grid thead");
    const tbody = document.querySelector("#grid tbody");
    thead.innerHTML = "";
    tbody.innerHTML = "";
    const trh = document.createElement("tr");
    state.visibleKeys.forEach((k) => {
      const th = document.createElement("th");
      const def = state.colDefs[k];
      const label = def ? def.label : mapKey(k);
      if (isNumericCol(k) || k === "favorite") {
        th.classList.add("th-numeric");
        if (k !== "favorite" && state.sortKey === k) th.classList.add("th-sorted");
        if (k === "favorite" ? state.favOnly : colFilterActive(k)) th.classList.add("th-filtered");
        const inner = document.createElement("div");
        inner.className = "th-inner";
        const lab = document.createElement("span");
        lab.className = "th-label";
        lab.textContent = label;
        const mark = document.createElement("span");
        mark.className = "th-sort-mark";
        if (k !== "favorite" && state.sortKey === k) {
          mark.textContent = state.sortDir === "desc" ? "↓" : "↑";
        }
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "th-filter-btn";
        btn.title = k === "favorite"
          ? "お気入りフィルタ"
          : "ソート / フィルタ";
        btn.textContent = "▼";
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          if (k === "favorite") openFavFilterMenu(th);
          else openFilterMenu(th, k);
        });
        inner.appendChild(lab);
        inner.appendChild(mark);
        inner.appendChild(btn);
        th.appendChild(inner);
      } else {
        th.textContent = label;
      }
      trh.appendChild(th);
    });
    thead.appendChild(trh);

    rows.forEach((row) => {
      const code = String(row.code).padStart(4, "0");
      const tr = document.createElement("tr");
      tr.dataset.code = code;
      if (state.selected === code) tr.classList.add("selected");
      if (state.hovered === code && state.selected !== code) tr.classList.add("is-hover");
      state.visibleKeys.forEach((k) => {
        const td = document.createElement("td");
        const def = state.colDefs[k] || { kind: "text" };
        if (def.kind === "signed1") td.classList.add("num");
        if (def.kind === "news_bundle") td.classList.add("news-bundle");
        if (def.kind === "favorite") td.classList.add("fav-cell");
        td.innerHTML = cellHtml(row, k);
        const st = cellStyle(row, k);
        if (st) {
          if (st.bg) td.style.backgroundColor = st.bg;
          if (st.fg) td.style.color = st.fg;
        }
        tr.appendChild(td);
      });
      tr.querySelectorAll("button.fav-star").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          if (state.freePreview) return;
          toggleFavorite(btn.dataset.favCode || code);
        });
      });
      tr.addEventListener("mouseenter", () => setHoveredCode(code, { from: "table" }));
      tr.addEventListener("mouseleave", () => {
        if (state.hovered === code) setHoveredCode(null);
      });
      tr.addEventListener("click", () => {
        selectCode(code, { scrollChart: true });
      });
      tbody.appendChild(tr);
    });
    syncChartsFromTable(rows);
  }

  function yZ(z) {
    if (z == null || Number.isNaN(Number(z))) return null;
    return Number(z) / 5;
  }


  function strokeSignedLine(ctx, arr, xAt, yAt, widthPx, alpha, dpr) {
    // Draw opaque polylines on an offscreen canvas, then blit with globalAlpha.
    // This keeps alpha uniform (no darkening at vertices from overlapping segments).
    const off = document.createElement("canvas");
    off.width = ctx.canvas.width;
    off.height = ctx.canvas.height;
    const o = off.getContext("2d");
    o.lineWidth = widthPx * dpr;
    o.lineCap = "round";
    o.lineJoin = "round";
    o.miterLimit = 2;

    const pos = "rgb(" + RS_POS + ")";
    const neg = "rgb(" + RS_NEG + ")";

    let path = [];
    let pathColor = null;

    function flush() {
      if (path.length < 2) {
        path = [];
        pathColor = null;
        return;
      }
      o.strokeStyle = pathColor;
      o.beginPath();
      o.moveTo(path[0].x, path[0].y);
      for (let i = 1; i < path.length; i++) o.lineTo(path[i].x, path[i].y);
      o.stroke();
      path = [];
      pathColor = null;
    }

    function colorFor(v) {
      return v >= 0 ? pos : neg;
    }

    let prev = null;
    for (let i = 0; i < arr.length; i++) {
      const raw = arr[i];
      if (raw == null || Number.isNaN(Number(raw))) {
        flush();
        prev = null;
        continue;
      }
      const v = Number(raw);
      const cur = { x: xAt(i), y: yAt(v), v };
      if (!prev) {
        path = [cur];
        pathColor = colorFor(v);
        prev = cur;
        continue;
      }

      const crossed = (prev.v > 0 && v < 0) || (prev.v < 0 && v > 0);
      if (crossed) {
        const t = prev.v / (prev.v - v);
        const mid = {
          x: prev.x + (cur.x - prev.x) * t,
          y: yAt(0),
          v: 0,
        };
        pathColor = colorFor(prev.v);
        path.push(mid);
        flush();
        path = [mid, cur];
        pathColor = colorFor(v);
      } else {
        path.push(cur);
        pathColor = colorFor(v !== 0 ? v : prev.v);
      }
      prev = cur;
    }
    flush();

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.drawImage(off, 0, 0);
    ctx.restore();
  }

  function drawZBars(ctx, arr, xAt, yAt, n, barW, dpr) {
    const y0 = yAt(0);
    const bw = Math.max(1 * dpr, barW);
    const zMeta = SERIES_META.find((s) => s.id === "z_disp");
    ctx.fillStyle = (zMeta && zMeta.color) || "rgba(196,192,242,0.34)";
    for (let i = 0; i < n; i++) {
      const raw = arr[i];
      const v = yZ(raw);
      if (v == null || Number.isNaN(v)) continue;
      const x = xAt(i);
      const y = yAt(v);
      const top = Math.min(y, y0);
      const height = Math.abs(y0 - y);
      if (height < 0.5) continue;
      ctx.fillRect(x - bw / 2, top, bw, height);
    }
  }

  // Visible window height stays 2 (default [-1, +1]). Drag pans center;
  // window must stay inside world [-2, +5] => center shift in [-1, +4].
  const CHART_Y_HALF = 1;
  const CHART_Y_WORLD_MIN = -2;
  const CHART_Y_WORLD_MAX = 5;
  const CHART_Y_SHIFT_MIN = CHART_Y_WORLD_MIN + CHART_Y_HALF; // -1
  const CHART_Y_SHIFT_MAX = CHART_Y_WORLD_MAX - CHART_Y_HALF; // +4

  function clampChartYShift(shift) {
    const s = Number(shift);
    if (!Number.isFinite(s)) return 0;
    return Math.max(CHART_Y_SHIFT_MIN, Math.min(CHART_Y_SHIFT_MAX, s));
  }

  function chartTickValues(ymin, ymax) {
    const span = ymax - ymin;
    const step = span <= 2.5 ? 0.5 : 1;
    const start = Math.ceil(ymin / step) * step;
    const ticks = [];
    for (let t = start; t <= ymax + 1e-9; t += step) {
      ticks.push(Math.round(t * 1000) / 1000);
    }
    return ticks;
  }

  function drawChart(canvas, dates, seriesMap, hoverEl, yShift) {
    const ctx = canvas.getContext("2d");
    const dpr = devicePixelRatio || 1;
    const cssW = Math.max(300, canvas.clientWidth || 300);
    const cssH = 225;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = CHART_BG;
    ctx.fillRect(0, 0, w, h);
    const padL = 36 * dpr, padR = 10 * dpr, padT = 10 * dpr, padB = 22 * dpr;
    const shift = clampChartYShift(yShift == null ? 0 : yShift);
    const ymin = -CHART_Y_HALF + shift;
    const ymax = CHART_Y_HALF + shift;
    const n = dates.length;
    if (!n) return;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    // Inset x so end Z-bars (width 0.7 * plotW/n) stay inside the plot.
    const zBarW = Math.max(1 * dpr, (plotW / Math.max(n, 1)) * 0.7);
    const xInset = zBarW / 2;
    const xSpan = Math.max(0, plotW - 2 * xInset);
    const xAt = (i) => padL + xInset + xSpan * (n === 1 ? 0.5 : i / (n - 1));
    const yAt = (v) => padT + plotH * (1 - (v - ymin) / (ymax - ymin));

    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.fillStyle = "rgba(200,210,230,0.75)";
    ctx.font = (10 * dpr) + "px sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    chartTickValues(ymin, ymax).forEach((tick) => {
      const y = yAt(tick);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      const label = Object.is(tick, -0) || tick === 0 ? "0" : String(tick);
      ctx.fillText(label, padL - 4 * dpr, y);
    });
    const xIdx = [0, Math.floor((n - 1) / 2), n - 1];
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    xIdx.forEach((i) => {
      const x = xAt(i);
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, h - padB);
      ctx.stroke();
      ctx.fillText(String(dates[i] || "").slice(5), x, h - padB + 4 * dpr);
    });

    // Clip series to plot area so pan edges stay clean.
    ctx.save();
    ctx.beginPath();
    ctx.rect(padL, padT, plotW, plotH);
    ctx.clip();
    SERIES_META.forEach((s) => {
      const arr = seriesMap[s.id] || [];
      if (s.kind === "bar") {
        drawZBars(ctx, arr, xAt, yAt, n, zBarW, dpr);
      } else {
        strokeSignedLine(ctx, arr, xAt, yAt, s.width, s.alpha, dpr);
      }
    });
    ctx.restore();

    // Overflow edge markers. Width = RS31. Color = RS green/red, or Z color if only Z overflows.
    let topRs = false, topZ = false, botRs = false, botZ = false;
    SERIES_META.forEach((s) => {
      const arr = seriesMap[s.id] || [];
      for (let i = 0; i < arr.length; i++) {
        const raw = arr[i];
        if (raw == null || Number.isNaN(Number(raw))) continue;
        const v = s.kind === "bar" ? yZ(raw) : Number(raw);
        if (v == null || Number.isNaN(v)) continue;
        if (v > ymax) {
          if (s.kind === "bar") topZ = true;
          else topRs = true;
        }
        if (v < ymin) {
          if (s.kind === "bar") botZ = true;
          else botRs = true;
        }
      }
    });
    const rs31 = SERIES_META.find((s) => s.id === "rs31") || { width: 1, alpha: 1 };
    const zMeta = SERIES_META.find((s) => s.id === "z_disp");
    const zEdgeColor = (zMeta && zMeta.color) || "rgba(196,192,242,0.34)";
    const edgeW = (rs31.width || 1) * dpr;
    function strokeOverflowEdge(yPix, strokeStyle, useRsAlpha) {
      ctx.save();
      if (useRsAlpha) ctx.globalAlpha = rs31.alpha == null ? 1 : rs31.alpha;
      ctx.strokeStyle = strokeStyle;
      ctx.lineWidth = edgeW;
      ctx.lineCap = "butt";
      ctx.beginPath();
      ctx.moveTo(padL, yPix);
      ctx.lineTo(padL + plotW, yPix);
      ctx.stroke();
      ctx.restore();
    }
    if (topRs || topZ) {
      const style = topRs ? ("rgb(" + RS_POS + ")") : zEdgeColor;
      strokeOverflowEdge(padT + edgeW / 2, style, !!topRs);
    }
    if (botRs || botZ) {
      const style = botRs ? ("rgb(" + RS_NEG + ")") : zEdgeColor;
      strokeOverflowEdge(padT + plotH - edgeW / 2, style, !!botRs);
    }

    canvas._chartGeom = {
      dpr: dpr,
      padL: padL,
      padT: padT,
      plotW: plotW,
      plotH: plotH,
      cssPlotH: plotH / dpr,
      ymin: ymin,
      ymax: ymax,
      shift: shift,
      n: n,
      xAt: xAt,
    };
  }

  function updateChartHover(canvas, dates, seriesMap, hoverEl, clientX) {
    const geom = canvas._chartGeom;
    if (!geom || !hoverEl) return;
    const rect = canvas.getBoundingClientRect();
    const x = (clientX - rect.left) * geom.dpr;
    let best = 0, bestDist = Infinity;
    for (let i = 0; i < geom.n; i++) {
      const d = Math.abs(geom.xAt(i) - x);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    const parts = [dates[best]];
    SERIES_META.forEach((s) => {
      const raw = (seriesMap[s.id] || [])[best];
      if (raw == null || Number.isNaN(Number(raw))) {
        parts.push(s.label + "=null");
      } else if (s.id === "z_disp") {
        parts.push(s.label + "=" + fmtSigned1(raw) + " (disp=" + fmtSigned1(Number(raw) / 5) + ")");
      } else {
        parts.push(s.label + "=" + fmtSigned1(raw));
      }
    });
    hoverEl.textContent = parts.join(" | ");
  }

  function bindChartPan(canvas, dates, seriesMap, hoverEl) {
    if (!canvas || canvas.dataset.panBound === "1") return;
    canvas.dataset.panBound = "1";
    canvas.style.cursor = "grab";
    canvas._chartYShift = 0;
    canvas._chartPan = null;

    const redraw = (shift) => {
      canvas._chartYShift = clampChartYShift(shift);
      drawChart(canvas, dates, seriesMap, hoverEl, canvas._chartYShift);
    };

    const endPan = () => {
      if (!canvas._chartPan) return;
      const pan = canvas._chartPan;
      canvas._chartPan = null;
      window.removeEventListener("pointermove", pan.onMove);
      window.removeEventListener("pointerup", pan.onUp);
      window.removeEventListener("pointercancel", pan.onUp);
      canvas.style.cursor = "grab";
      canvas.classList.remove("is-panning");
      // Release -> snap back to 0-centered default view.
      redraw(0);
    };

    canvas.addEventListener("pointerdown", (ev) => {
      if (ev.button != null && ev.button !== 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      const startShift = canvas._chartYShift || 0;
      const pan = {
        pointerId: ev.pointerId,
        startY: ev.clientY,
        startShift: startShift,
        moved: false,
        onMove: null,
        onUp: null,
      };
      pan.onMove = (e) => {
        if (e.pointerId !== pan.pointerId) return;
        const dy = e.clientY - pan.startY;
        if (Math.abs(dy) > 3) pan.moved = true;
        const geom = canvas._chartGeom;
        const cssPlotH = (geom && geom.cssPlotH) || 193;
        // Drag down -> view higher values (paper-grab feel).
        const next = pan.startShift + (dy / cssPlotH) * (CHART_Y_HALF * 2);
        redraw(next);
        updateChartHover(canvas, dates, seriesMap, hoverEl, e.clientX);
      };
      pan.onUp = (e) => {
        if (e.pointerId !== pan.pointerId) return;
        if (pan.moved) canvas._suppressClick = true;
        endPan();
      };
      canvas._chartPan = pan;
      canvas.style.cursor = "grabbing";
      canvas.classList.add("is-panning");
      window.addEventListener("pointermove", pan.onMove);
      window.addEventListener("pointerup", pan.onUp);
      window.addEventListener("pointercancel", pan.onUp);
    });

    canvas.addEventListener("pointermove", (ev) => {
      if (canvas._chartPan) return;
      updateChartHover(canvas, dates, seriesMap, hoverEl, ev.clientX);
    });
  }


  function asOfQuery() {
    return "as_of=" + encodeURIComponent(state.asOf || "");
  }

  async function fetchSeries(codes) {
    const missing = codes.filter((c) => !state.seriesCache[c]);
    if (!missing.length) return;
    for (let i = 0; i < missing.length; i += 80) {
      const chunk = missing.slice(i, i + 80);
      const res = await fetch("/api/series?" + asOfQuery() + "&codes=" + encodeURIComponent(chunk.join(",")));
      const data = await res.json();
      Object.assign(state.seriesCache, data.series || {});
    }
  }


  function findRowByCode(code) {
    if (!code) return null;
    const c = String(code).padStart(4, "0");
    return state.rows.find((r) => String(r.code).padStart(4, "0") === c) || null;
  }

  function scrollTableRowIntoView(code) {
    const tr = document.querySelector('#grid tbody tr[data-code="' + code + '"]');
    if (tr) tr.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function scrollChartCardIntoView(code) {
    const card = document.querySelector('#chart-host .chart-card[data-code="' + code + '"]');
    if (card) card.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function syncHighlightClasses() {
    const sel = state.selected;
    const hov = state.hovered;
    document.querySelectorAll("#grid tbody tr[data-code]").forEach((tr) => {
      const c = tr.dataset.code;
      tr.classList.toggle("selected", !!sel && c === sel);
      tr.classList.toggle("is-hover", !!hov && c === hov && c !== sel);
    });
    document.querySelectorAll("#chart-host .chart-card[data-code]").forEach((card) => {
      const c = card.dataset.code;
      card.classList.toggle("selected", !!sel && c === sel);
      card.classList.toggle("is-hover", !!hov && c === hov && c !== sel);
    });
  }

  function setHoveredCode(code, opts) {
    opts = opts || {};
    const next = code ? String(code).padStart(4, "0") : null;
    const changed = state.hovered !== next;
    state.hovered = next;
    if (changed) syncHighlightClasses();
    if (!next) return;
    // Keep counterpart in view while hovering (nearest = no-op if already visible).
    if (opts.from === "table") scrollChartCardIntoView(next);
    else if (opts.from === "chart") scrollTableRowIntoView(next);
  }

  function selectCode(code, opts) {
    opts = opts || {};
    const next = code ? String(code).padStart(4, "0") : null;
    const row = findRowByCode(next);
    state.selected = next;
    if (next) state.hovered = next;
    syncHighlightClasses();
    if (opts.scrollTable && next) scrollTableRowIntoView(next);
    if (opts.scrollChart && next) scrollChartCardIntoView(next);
    if (row) loadKabutan(row);
    else showWebEmpty();
  }

  function syncChartsFromTable(rows) {
    const list = rows || displayRows();
    const codes = list.map((r) => String(r.code).padStart(4, "0"));
    state.visibleChartCodes = codes;
    refreshCharts(codes);
  }

  async function paintChartCard(card) {
    if (!card || card.dataset.drawn === "1") return;
    const code = card.dataset.code;
    const gen = state.chartBuildId;
    await fetchSeries([code]);
    if (gen !== state.chartBuildId) return;
    if (!card.isConnected || card.dataset.code !== code) return;
    let canvas = card.querySelector("canvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      const slot = card.querySelector(".chart-slot");
      if (slot) slot.replaceWith(canvas);
      else card.appendChild(canvas);
    }
    const metrics = state.seriesCache[code];
    if (!metrics) return;
    const values = metrics.values || {};
    const b = state.bench;
    const dates = (state.meta && state.meta.axis_dates) || [];
    const seriesMap = {
      rs31: values["rs31_" + b] || [],
      rs63: values["rs63_" + b] || [],
      rs126: values["rs126_" + b] || [],
      rs252: values["rs252_" + b] || [],
      rs_sma75: values["rs_sma75_" + b] || [],
      z_disp: values.z_turnover_60 || [],
    };
    const hoverEl = card.querySelector(".hover");
    drawChart(canvas, dates, seriesMap, hoverEl, 0);
    bindChartPan(canvas, dates, seriesMap, hoverEl);
    card.dataset.drawn = "1";
  }

  function refreshCharts(codes) {
    const host = $("chart-host");
    if (!host) return;
    // Preserve table order exactly (codes already ordered). Dedupe while keeping first index.
    const seen = new Set();
    const ordered = [];
    (codes || []).forEach((c) => {
      const code = String(c).padStart(4, "0");
      if (seen.has(code)) return;
      seen.add(code);
      ordered.push(code);
    });

    state.chartBuildId = (state.chartBuildId || 0) + 1;
    if (state.chartObserver) {
      state.chartObserver.disconnect();
      state.chartObserver = null;
    }

    const prevScroll = host.scrollTop;
    host.innerHTML = "";
    const frag = document.createDocumentFragment();
    const cards = [];
    ordered.forEach((code) => {
      const row = findRowByCode(code) || {};
      const card = document.createElement("div");
      card.className = "chart-card";
      card.dataset.code = code;
      if (state.selected === code) card.classList.add("selected");
      if (state.hovered === code && state.selected !== code) card.classList.add("is-hover");
      card.innerHTML =
        "<h4>" + escapeHtml(code) + " " + escapeHtml(row.name || "") + "</h4>" +
        "<div class=\"hover\"></div>" +
        "<div class=\"chart-slot\" aria-hidden=\"true\"></div>";
      card.addEventListener("mouseenter", () => setHoveredCode(code, { from: "chart" }));
      card.addEventListener("mouseleave", () => {
        if (state.hovered === code) setHoveredCode(null);
      });
      card.addEventListener("click", (ev) => {
        const canvas = card.querySelector("canvas");
        if (canvas && canvas._suppressClick) {
          canvas._suppressClick = false;
          ev.preventDefault();
          ev.stopPropagation();
          return;
        }
        selectCode(code, { scrollTable: true });
      });
      frag.appendChild(card);
      cards.push(card);
    });
    host.appendChild(frag);

    state.chartObserver = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) paintChartCard(en.target);
      });
    }, { root: host, rootMargin: "160px 0px", threshold: 0.01 });

    cards.forEach((card) => state.chartObserver.observe(card));

    // Restore scroll if list length similar; otherwise keep top / focus selection.
    host.scrollTop = prevScroll;
    if (state.selected) scrollChartCardIntoView(state.selected);
    else if (state.hovered) scrollChartCardIntoView(state.hovered);
  }




  const TAB_SETTINGS_DEFAULT = {
    overview: true,
    chart: true,
    news: true,
    news_candidates: true,
    link_buffett: false,
    link_minkabu: false,
    link_yahoo: false,
  };
  const TAB_SETTINGS_META = [
    { key: "overview", label: "\u6982\u8981\uff08\u682a\u63a2\uff09" },
    { key: "chart", label: "\u30c1\u30e3\u30fc\u30c8\uff08\u682a\u63a2\uff09" },
    { key: "news", label: "\u30cb\u30e5\u30fc\u30b9\uff08\u682a\u63a2\uff09" },
    { key: "news_candidates", label: "\u30cb\u30e5\u30fc\u30b9\u5019\u88dc" },
    { key: "link_buffett", label: "\u30d0\u30d5\u30a7\u30c3\u30c8\u30b3\u30fc\u30c9" },
    { key: "link_minkabu", label: "\u307f\u3093\u304b\u3076" },
    { key: "link_yahoo", label: "Yahoo!\u30d5\u30a1\u30a4\u30ca\u30f3\u30b9" },
  ];
  const TAB_SETTINGS_KEY = "web_ui_asof_tab_settings_v1";

  function loadTabSettings() {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(TAB_SETTINGS_KEY) || "{}") || {};
    } catch (_) {
      saved = {};
    }
    state.tabSettings = { ...TAB_SETTINGS_DEFAULT, ...saved };
  }

  function saveTabSettings() {
    localStorage.setItem(TAB_SETTINGS_KEY, JSON.stringify(state.tabSettings));
  }

  function openTabSettingsModal() {
    renderTabSettingsPanel();
    const modal = $("tab-settings-modal");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeTabSettingsModal() {
    const modal = $("tab-settings-modal");
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  function renderTabSettingsPanel() {
    const panel = $("tab-settings-panel");
    if (!panel) return;
    panel.innerHTML = "";
    TAB_SETTINGS_META.forEach((meta) => {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.tabSettings[meta.key];
      cb.addEventListener("change", () => {
        state.tabSettings[meta.key] = cb.checked;
        saveTabSettings();
        const row = state.rows.find((r) => String(r.code).padStart(4, "0") === state.selected) || null;
        renderKabutanTabBar(row);
        if (row) applyKabutanUrl(row, state.kabutanMode);
        else showWebEmpty();
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + meta.label));
      panel.appendChild(lab);
    });
  }

  function firstAvailableTabMode(row) {
    for (const key of ["overview", "chart", "news", "link_buffett", "link_minkabu", "link_yahoo"]) {
      if (!state.tabSettings[key]) continue;
      if (key.startsWith("link_") && row && !row[key]) continue;
      return key;
    }
    if (state.tabSettings.news_candidates && row) {
      if (isUnknownMaterialRow(row)) return "overview";
      const items = eventNewsItems(row).filter((it) => it.title !== UNKNOWN_MATERIAL_TEXT && it.url);
      if (items.length) return "cand:" + items[0].n;
    }
    return "overview";
  }

  function ensureValidKabutanMode(row) {
    const mode = state.kabutanMode;
    if (mode === "overview" || mode === "chart" || mode === "news") {
      if (!state.tabSettings[mode]) state.kabutanMode = firstAvailableTabMode(row);
      return;
    }
    if (String(mode).startsWith("cand:")) {
      if (!state.tabSettings.news_candidates || isUnknownMaterialRow(row)) {
        state.kabutanMode = firstAvailableTabMode(row);
      }
      return;
    }
    if (mode === "link_buffett" || mode === "link_minkabu" || mode === "link_yahoo") {
      if (!state.tabSettings[mode] || (row && !row[mode])) {
        state.kabutanMode = firstAvailableTabMode(row);
      }
    }
  }

  function renderKabutanTabBar(row) {
    const main = $("kabutan-tabs-main");
    if (!main) return;
    if (!state.tabSettings) loadTabSettings();
    main.innerHTML = "";

    const baseLabels = { overview: "\u6982\u8981", chart: "\u30c1\u30e3\u30fc\u30c8", news: "\u30cb\u30e5\u30fc\u30b9" };
    ["overview", "chart", "news"].forEach((id) => {
      if (!state.tabSettings[id]) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kab = id;
      btn.textContent = baseLabels[id];
      main.appendChild(btn);
    });

    ["link_buffett", "link_minkabu", "link_yahoo"].forEach((id) => {
      if (!state.tabSettings[id]) return;
      const meta = TAB_SETTINGS_META.find((x) => x.key === id);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kab = id;
      btn.textContent = meta ? meta.label : id;
      if (row && !row[id]) {
        btn.disabled = true;
        btn.title = "URL\u306a\u3057";
      }
      main.appendChild(btn);
    });

    if (state.tabSettings.news_candidates && row) {
      if (isUnknownMaterialRow(row)) {
        const span = document.createElement("span");
        span.className = "kabutan-unknown-material";
        span.textContent = UNKNOWN_MATERIAL_TEXT;
        main.appendChild(span);
      } else {
        const items = eventNewsItems(row).filter((it) => it.title !== UNKNOWN_MATERIAL_TEXT);
        items.forEach((it) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.dataset.cand = String(it.n);
          btn.dataset.kab = "cand:" + it.n;
          btn.textContent = tabLabel10(it.title);
          btn.title = it.title + (it.url ? ("\n" + it.url) : "");
          btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            state.kabutanMode = "cand:" + it.n;
            setKabutanActive(state.kabutanMode);
            applyKabutanUrl(row, state.kabutanMode);
          });
          main.appendChild(btn);
        });
      }
    }

    ensureValidKabutanMode(row);
    setKabutanActive(state.kabutanMode);
  }

  function isLikelyUnframeable(url) {
    if (!url) return false;
    const u = String(url).toLowerCase();
    if (/\.pdf(?:$|[?#])/.test(u)) return true;
    if (u.includes("application/pdf")) return true;
    if (u.includes("release.tdnet.info")) return true;
    if (u.includes("/inbs/") && u.includes("tdnet")) return true;
    return false;
  }

  function setOpenTabVisible(url) {
    const btn = $("kabutan-blank");
    if (!btn) return;
    if (url) {
      btn.href = url;
      btn.classList.remove("hidden");
    } else {
      btn.href = "#";
      btn.classList.add("hidden");
    }
  }

  function showWebEmpty() {
    const frame = $("kabutan-frame");
    const empty = $("kabutan-empty");
    const blocked = $("kabutan-blocked");
    if (state.kabutanTimer) {
      clearTimeout(state.kabutanTimer);
      state.kabutanTimer = null;
    }
    if (frame) {
      frame.src = "about:blank";
      frame.classList.add("is-empty");
      frame.classList.remove("is-blocked");
    }
    if (empty) empty.classList.remove("hidden");
    if (blocked) blocked.classList.add("hidden");
    setOpenTabVisible(null);
  }

  function showWebBlocked(url, reason) {
    const frame = $("kabutan-frame");
    const empty = $("kabutan-empty");
    const blocked = $("kabutan-blocked");
    const reasonEl = $("kabutan-blocked-reason");
    const openBtn = $("kabutan-blocked-open");
    if (empty) empty.classList.add("hidden");
    if (blocked) blocked.classList.remove("hidden");
    if (reasonEl) reasonEl.textContent = reason || "";
    if (openBtn) {
      openBtn.href = url || "#";
      openBtn.classList.toggle("hidden", !url);
    }
    if (frame) {
      frame.src = "about:blank";
      frame.classList.add("is-blocked");
      frame.classList.remove("is-empty");
    }
    setOpenTabVisible(url);
  }

  function showWebFrame(url) {
    const frame = $("kabutan-frame");
    const empty = $("kabutan-empty");
    const blocked = $("kabutan-blocked");
    if (empty) empty.classList.add("hidden");
    if (blocked) blocked.classList.add("hidden");
    if (frame) {
      frame.classList.remove("is-empty");
      frame.classList.remove("is-blocked");
    }
    setOpenTabVisible(url);
  }

  function kabutanUrl(row, mode) {
    const code = String(row.code).padStart(4, "0");
    if (mode && String(mode).startsWith("cand:")) {
      const n = String(mode).slice(5);
      const url = row["event_news_" + n + "_url"];
      return url ? String(url) : null;
    }
    if (mode === "link_buffett" || mode === "link_minkabu" || mode === "link_yahoo") {
      return row[mode] ? String(row[mode]) : null;
    }
    if (mode === "chart") return "https://kabutan.jp/stock/chart?code=" + code;
    if (mode === "news") return "https://kabutan.jp/stock/news?code=" + code;
    return "https://kabutan.jp/stock/?code=" + code;
  }

  function setKabutanActive(mode) {
    const host = $("kabutan-tabs-main") || document.querySelector(".kabutan-tabs");
    if (!host) return;
    host.querySelectorAll("[data-kab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.kab === mode);
    });
  }

  function applyKabutanUrl(row, mode) {
    if (!row) {
      showWebEmpty();
      return;
    }
    const m = mode || state.kabutanMode;
    let url = kabutanUrl(row, m);
    if (!url && String(m).startsWith("cand:")) {
      url = null;
    } else if (!url) {
      url = kabutanUrl(row, "overview");
    }
    const frame = $("kabutan-frame");
    if (!url) {
      showWebBlocked(null, "\u8868\u793a\u3067\u304d\u308b URL \u304c\u3042\u308a\u307e\u305b\u3093\u3002");
      return;
    }

    const isCand = String(m).startsWith("cand:");
    if (isCand) {
      frame.removeAttribute("sandbox");
    } else {
      frame.setAttribute(
        "sandbox",
        "allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      );
    }

    if (isLikelyUnframeable(url)) {
      showWebBlocked(
        url,
        "PDF \u307e\u305f\u306f\u57cb\u3081\u8fbc\u307f\u975e\u5bfe\u5fdc\u306e\u30da\u30fc\u30b8\u306e\u305f\u3081\u3001\u3053\u306e\u9818\u57df\u3067\u306f\u8868\u793a\u3067\u304d\u307e\u305b\u3093\u3002\u5225\u30bf\u30d6\u3067\u958b\u3044\u3066\u304f\u3060\u3055\u3044\u3002"
      );
      return;
    }

    showWebFrame(url);
    if (state.kabutanTimer) clearTimeout(state.kabutanTimer);
    frame.src = "about:blank";
    setTimeout(() => {
      frame.src = url;
    }, 0);
  }


  function syncCandTabs(row) {
    renderKabutanTabBar(row || null);
  }


  function loadKabutan(row) {
    // rebuild candidate tabs for the selected row, then show current mode URL
    syncCandTabs(row);
    applyKabutanUrl(row, state.kabutanMode);
  }

  function fillAsOfSelect() {
    const sel = $("asof-mode");
    sel.innerHTML = "";
    state.availableDates.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      if (d === state.asOf) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function updateBanner() {
    $("asof-banner").textContent =
      "as-of=" + state.meta.as_of +
      " rows=" + state.meta.n_rows +
      " excluded=" + state.meta.n_excluded +
      " axis=" + ((state.meta.axis_dates || []).length) +
      " | 指標・価格情報=cache再計算 / ニュース等=CSV由来 | (not Track D)";
  }

  async function loadSnapshot(asOf) {
    state.asOf = asOf;
    state.seriesCache = {};
    state.visibleChartCodes = [];
    state.selected = null;
    state.hovered = null;
    $("chart-host").innerHTML = "";
    showWebEmpty();
    state.kabutanMode = "overview";
    renderKabutanTabBar(null);

    state.meta = await (await fetch("/api/meta?" + asOfQuery())).json();
    const payload = await (await fetch("/api/rows?" + asOfQuery())).json();
    state.rows = payload.rows || [];
    const keySet = new Set();
    state.rows.forEach((r) => Object.keys(r).forEach((k) => keySet.add(k)));
    state.allKeys = [...keySet].sort();
    ensureColDefs();
    // date は表にも列出し隠しにも出さない
    state.visibleKeys = XLSX_DEFAULT.map((c) => c.key).filter((k) => {
      if (k === "date" || HIDDEN_COL_KEYS.has(k)) return false;
      if (LINK_KEYS_OPTIONAL.has(k)) return false;
      if (k === "favorite") return true;
      if (k === "event_news_bundle") {
        return (
          state.allKeys.includes("event_news_bundle") ||
          state.allKeys.includes("event_news_1_title") ||
          state.allKeys.includes("event_news_2_title") ||
          state.allKeys.includes("event_news_3_title") ||
          state.rows.some((r) => eventNewsItems(r).length)
        );
      }
      if (k === "rs_sma75_topix") {
        return state.allKeys.includes("rs_sma75_topix") || state.allKeys.includes("rs_sma75_nikkei");
      }
      return state.allKeys.includes(k) || state.allKeys.includes(mapKey(k));
    });

    updateBanner();
    fillAsOfSelect();
    renderColsPanel();
    renderTable();
  }

  async function boot() {
    const datesPayload = await (await fetch("/api/dates")).json();
    state.availableDates = datesPayload.dates || [];
    state.asOf = datesPayload.default || (state.availableDates[state.availableDates.length - 1] || null);
    if (!state.asOf) throw new Error("no as-of snapshots available");

    $("asof-mode").addEventListener("change", (e) => {
      loadSnapshot(e.target.value).catch((err) => {
        $("asof-banner").textContent = "as-of switch failed: " + err;
      });
    });
    $("bench-mode").addEventListener("change", (e) => {
      state.bench = e.target.value;
      state.visibleChartCodes = [];
      $("chart-host").innerHTML = "";
      renderTable();
    });
    // favorites: per-user localStorage (prototype auth substitute)
    const savedUser = localStorage.getItem("web_ui_asof_fav_user") || "local";
    state.userId = savedUser;
    state.favorites = loadFavorites(state.userId);
    if ($("fav-user")) $("fav-user").value = state.userId;

    $("fav-user").addEventListener("change", () => {
      if (state.freePreview) return;
      const next = ($("fav-user").value || "local").trim() || "local";
      state.userId = next;
      localStorage.setItem("web_ui_asof_fav_user", next);
      state.favorites = loadFavorites(next);
      renderTable();
    });

    $("free-preview").addEventListener("change", (e) => {
      state.freePreview = e.target.checked;
      if (state.freePreview) {
        state.sortKey = "z_turnover_60";
        state.sortDir = "desc";
        state.favOnly = false;
        state.excludeAllRsNeg = false;
        if ($("filter-exclude-all-rs-neg")) $("filter-exclude-all-rs-neg").checked = false;
        closeFilterMenu();
        setFavoritesUiEnabled(false);
      } else {
        setFavoritesUiEnabled(true);
      }
      syncFilterModalUi();
      state.visibleChartCodes = [];
      $("chart-host").innerHTML = "";
      renderTable();
    });
    setFavoritesUiEnabled(!state.freePreview);
    syncFilterModalUi();
    $("cols-toggle").addEventListener("click", () => openColsModal());
    $("cols-modal-close").addEventListener("click", () => closeColsModal());
    $("cols-modal-done").addEventListener("click", () => closeColsModal());
    $("cols-modal").addEventListener("click", (ev) => {
      if (ev.target && ev.target.getAttribute("data-cols-close") === "1") closeColsModal();
    });

    $("filter-toggle").addEventListener("click", () => openFilterModal());
    $("tab-settings-toggle").addEventListener("click", () => openTabSettingsModal());
    $("tab-settings-close").addEventListener("click", () => closeTabSettingsModal());
    $("tab-settings-done").addEventListener("click", () => closeTabSettingsModal());
    $("tab-settings-modal").addEventListener("click", (ev) => {
      if (ev.target && ev.target.getAttribute("data-tab-settings-close") === "1") closeTabSettingsModal();
    });

    $("filter-modal-close").addEventListener("click", () => closeFilterModal());
    $("filter-modal-done").addEventListener("click", () => closeFilterModal());
    $("filter-modal").addEventListener("click", (ev) => {
      if (ev.target && ev.target.getAttribute("data-filter-close") === "1") closeFilterModal();
    });
    $("filter-exclude-all-rs-neg").addEventListener("change", (e) => {
      if (state.freePreview) {
        e.target.checked = false;
        state.excludeAllRsNeg = false;
        syncFilterModalUi();
        return;
      }
      state.excludeAllRsNeg = e.target.checked;
      state.visibleChartCodes = [];
      $("chart-host").innerHTML = "";
      renderTable();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape") return;
      if (!$("cols-modal").classList.contains("hidden")) closeColsModal();
      if (!$("filter-modal").classList.contains("hidden")) closeFilterModal();
      if (!$("tab-settings-modal").classList.contains("hidden")) closeTabSettingsModal();
      closeFilterMenu();
    });
    document.addEventListener("click", () => closeFilterMenu());
    $("kabutan-tabs-main").addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-kab]");
      if (!btn || !ev.currentTarget.contains(btn)) return;
      if (btn.hasAttribute("data-cand")) return;
      if (btn.disabled) return;
      ev.preventDefault();
      state.kabutanMode = btn.dataset.kab;
      setKabutanActive(state.kabutanMode);
      const row = state.rows.find((r) => String(r.code).padStart(4, "0") === state.selected);
      if (row) applyKabutanUrl(row, state.kabutanMode);
    });

    ensureColDefs();
    showWebEmpty();
    initKabutanSplitter();
    renderLegend();
    await loadSnapshot(state.asOf);
  }

  boot().catch((err) => {
    $("asof-banner").textContent = "boot failed: " + err;
  });
})();
