(() => {
  const XLSX_DEFAULT = [
    { key: "code", label: "コード", kind: "text" },
    { key: "name", label: "銘柄名", kind: "text" },
    { key: "favorite", label: "お気に入り", kind: "favorite" },
    { key: "link_kabutan", label: "概要（株探）", kind: "link", linkText: "株探" },
    { key: "link_kabutan_chart", label: "チャート（株探）", kind: "link", linkText: "チャート" },
    { key: "link_kabutan_news", label: "ニュース（株探）", kind: "link", linkText: "ニュース" },
    { key: "price_text", label: "当日の値動き", kind: "text" },
    { key: "z_turnover_60", label: "売買代金異常", kind: "signed1" },
    { key: "rs_acceleration_zscore_topix", label: "RSの加速Z", kind: "signed1", bench: true },
    { key: "rs_acceleration_topix", label: "RSの加速", kind: "signed1", bench: true },
    { key: "rs31_topix", label: "31日RS", kind: "signed1", bench: true },
    { key: "rs63_topix", label: "63日RS", kind: "signed1", bench: true },
    { key: "rs126_topix", label: "126日RS", kind: "signed1", bench: true },
    { key: "rs252_topix", label: "252日RS", kind: "signed1", bench: true },
    { key: "rs_sma75_topix", label: "75移動平均RS", kind: "signed1", bench: true },
    { key: "event_news_bundle", label: "売買代金異常 要因ニュース候補", kind: "news_bundle" },
    { key: "research_prompt_block", label: "調査用まとめ", kind: "text" },
  ];

  // Draw order = array order (back → front). Z bars first; RS lines by thickness.
  const CHART_BG = "rgb(9,7,32)";
  const RS_POS = "82,255,134";
  const RS_NEG = "255,65,0";
  const SERIES_META = [
    { id: "z_disp", label: "売買代金異常", kind: "bar", color: "rgba(196,192,242,0.34)" },
    { id: "rs_sma75", label: "75移動平均RS", kind: "line", width: 16, alpha: 0.1 },
    { id: "rs252", label: "252日RS", kind: "line", width: 8, alpha: 0.2 },
    { id: "rs126", label: "126日RS", kind: "line", width: 6, alpha: 0.4 },
    { id: "rs63", label: "63日RS", kind: "line", width: 4, alpha: 0.6 },
    { id: "rs31", label: "31日RS", kind: "line", width: 1, alpha: 1.0 },
  ];

  const LABEL_FAMILY_INDEX = "指数比 ＝ この銘柄のリターン − 比較指数のリターン（同じ期間、終値どうし）。 リターンは、その期間にどれだけ上がったかの割合で、下がればマイナス。 市場全体の動きを基準に、この銘柄の成績を比べる値。正なら指数より良く、負なら悪く、0 なら同じ。 割り算ではなく引き算なので、指数が下がった期間でも符号の意味は変わらない。 株価が下がっていても、指数より下げ幅が小さければ正になる。 +0.1 は10%分の差（指数 +5%・銘柄 +15% → +0.10。指数 −10%・銘柄 −4% → +0.06）。%表示ではない。";
  const LABEL_TIPS = {
  "code": {
    "text": "東証の4桁の証券コード。",
    "family": false
  },
  "name": {
    "text": "銘柄の名称。",
    "family": false
  },
  "favorite": {
    "text": "自分で保存したお気に入りリストに、この銘柄が入っているかどうか。 チップはリストの印で、強い・弱いを表す指標ではない。",
    "family": false
  },
  "price_text": {
    "text": "基準日の始値・高値・安値・終値から、その日の値動きの形を短い言葉で表したもの。 陽線（終値が始値より高い）、陰線（その逆）、上ヒゲ・下ヒゲ（一時的に大きく動いて戻した）、 上窓・下窓（前日の値幅から離れて始まった）、S高・S安（ストップ高・ストップ安。1日の値幅制限に達した疑い）など。",
    "family": false
  },
  "z_turnover_60": {
    "text": "基準日の売買代金（終値×出来高）が、この銘柄の普段（直近60営業日）と比べてどれだけ珍しい多さかを表す値。 ズレは標準偏差を1として測る。学校の偏差値と同じ考え方で、偏差値＝50＋10×Z。 0 が普段どおり、+1 でやや多め、+2 以上は普段ほとんど見ない多さ、負は普段より少ない。 株価ではなく売買代金のZ。「売買代金倍率」（普段の何倍か）とは別。",
    "family": false
  },
  "rs_acceleration_zscore": {
    "text": "「指数比の加速」が、この銘柄の普段（直近60営業日）と比べてどれだけ珍しい大きさかを表す値。 売買代金Zと同じ物差しで、0 が普段どおり、+2 以上は普段ほとんど見ない強い加速、−2 以下はその逆（偏差値＝50＋10×Z）。 加速そのものの大きさではないので、加速が小さくても、この銘柄の普段がもっと小さければ大きな値になる。",
    "family": false
  },
  "rs_acceleration": {
    "text": "「指数比 31日リターン」−「指数比 252日リターン」。直近約1か月半の指数比が、過去1年の指数比よりどれだけ高いか。 正なら、最近のほうが指数に対して勢いがある（例: 1年では指数に負けていたが、直近は勝っている）。負ならその逆。 グラフの線の傾きのことではない。「指数比の加速Z」（普段と比べた珍しさ）とも別。",
    "family": false
  },
  "rs31": {
    "text": "31営業日（約1か月半）のリターンの指数比。",
    "family": true
  },
  "rs63": {
    "text": "63営業日（約3か月）のリターンの指数比。",
    "family": true
  },
  "rs126": {
    "text": "126営業日（約半年）のリターンの指数比。",
    "family": true
  },
  "rs252": {
    "text": "252営業日（約1年）のリターンの指数比。「指数比の加速」は、指数比 31日リターンからこの値を引いた差。",
    "family": true
  },
  "rs_sma75": {
    "text": "この銘柄と比較指数それぞれの「75日線」（直近75営業日の終値の平均をつないだ線）が、31営業日でどれだけ上がったかの割合の差。 終値の代わりに、日々の上下をならした線で比べるので、流れとしてどちらが強いかが出る。 単位は指数比 31日リターンと同じで、1日あたりの傾きではない。指数比を75日で平均した線でも、75日リターンでもない。",
    "family": true
  },
  "event_news_bundle": {
    "text": "売買代金が急増した日に関係しそうなニュースの候補（最大3件）。原因と断定したものではない。 材料が見つからないときは「材料不明・需給起因疑い」などの文になる。",
    "family": false
  },
  "research_prompt_block": {
    "text": "この銘柄の基本情報（基準日・コード・銘柄名）と、当日の売買代金・値動きの指標を1行のテキストにまとめたもの。 自分で調べるときや AI に質問するときに、そのまま貼り付けて使える。結論は含まない。",
    "family": false
  },
  "beta_adjusted_rs": {
    "text": "1年（252営業日）のリターンから、「この銘柄が指数にどれだけ連動して動くか」（β、ベータ）×「指数のリターン」を引いた値。 βが1.5なら、指数が1%動くとこの銘柄は平均1.5%動くという意味。 指数比 252日リターンは連動の強さを1とみなして引くのに対し、こちらは銘柄ごとの連動の強さを考慮する。 正なら、指数に連動して動いた分を除いても上がっている。",
    "family": false
  },
  "information_ratio": {
    "text": "直近63営業日（約3か月）について、毎日の「この銘柄の前日比 − 比較指数の前日比」の平均を、そのばらつき（標準偏差）で割った値。 指数を上回る日が安定して続くほど正に大きく、下回る日が続くほど負に大きい。 日によってまちまちだと、平均が同じでも絶対値は小さくなる。 %でも倍率でもなく、指数比 63日リターンとは別の量。専門用語では情報比率。",
    "family": false
  },
  "perfect_order_days": {
    "text": "終値の25日・75日・200日移動平均線が、短い線ほど上に並んだ状態（25日線 > 75日線 > 200日線）が、基準日まで何営業日続いているか。 上昇の並びだけ数え、逆の並び（下降パーフェクトオーダー）は数えない。0 はその並びではない。 220営業日分（1年弱）の株価がない銘柄は空欄。",
    "family": false
  },
  "price_change_pct": {
    "text": "前営業日の終値に対する基準日終値の変化率。+3.0 なら前営業日より 3% 高い。 この列だけ値が%で、指数比の小数（0.1＝10%分）とは単位が違う。指数との比較は含まない。",
    "family": false
  },
  "turnover_ma_ratio_60": {
    "text": "基準日の売買代金が、この銘柄の直近60営業日平均の何倍か。1.0 が普段どおり、3.0 なら普段の3倍、0.5 なら半分。 「売買代金Z」と同じく普段と比べる値だが、こちらは倍率で、Zは珍しさの度合い。",
    "family": false
  },
  "as_of": {
    "text": "表とグラフがそろえている営業日。画面のすべての数値は、この日の終値までのデータで計算している。 「最終更新」はデータが確定した時刻で、基準日とは別。",
    "family": false
  },
  "benchmark": {
    "text": "「指数比〜」が比べる相手。TOPIX（東証の幅広い銘柄の指数）か日経平均（代表的な225銘柄の指数）。 切り替えると指数比の列とグラフが入れ替わる。 売買代金Z、当日の値動き、前日比(%)、売買代金倍率、パーフェクトオーダー日数は変わらない。",
    "family": false
  },
  "committed_at": {
    "text": "いま見ているデータが確定した時刻（日本時間）。基準日そのものではない。",
    "family": false
  },
  "exclude_all_rs_negative": {
    "text": "指数比 31日・63日・126日・252日リターンと、指数比 75日線の傾きがすべてマイナスの銘柄を一覧から外す。 下げ相場でも、指数より下げ幅が小さい銘柄は残る。指数比の加速と売買代金Zは見ない。",
    "family": false
  },
  "core_universe": {
    "text": "この画面が扱う銘柄の範囲。国内株式のうち、上場して間もない銘柄（約1年分の株価がまだない）と、 売買代金が少なく取引が薄い銘柄を除いたもの。画面の数値はすべてこの範囲の中で計算している。",
    "family": false
  },
  "web_overview": {
    "text": "株探（かぶたん）の銘柄概要ページを開く。",
    "family": false
  },
  "web_chart": {
    "text": "株探のチャートページを開く。この画面の指数比グラフとは別。",
    "family": false
  },
  "web_news": {
    "text": "株探のニュース一覧を開く。表の「ニュース候補」（売買代金が急増した日の候補）とは別。",
    "family": false
  },
  "web_news_candidates": {
    "text": "表の「ニュース候補」と同じ内容を、下段のタブで開く。",
    "family": false
  },
  "web_buffett": {
    "text": "バフェットコードの銘柄ページを開く。この画面のグラフや、表のニュース候補とは別のサイト。",
    "family": false
  },
  "web_minkabu": {
    "text": "みんかぶの銘柄ページを開く。この画面のグラフや、表のニュース候補とは別のサイト。",
    "family": false
  },
  "web_yahoo": {
    "text": "Yahoo!ファイナンスの銘柄ページを開く。この画面のグラフや、表のニュース候補とは別のサイト。",
    "family": false
  }
};
  const COLUMN_LABEL_IDS = {
  "code": "code",
  "name": "name",
  "favorite": "favorite",
  "price_text": "price_text",
  "candle_labels": "price_text",
  "z_turnover_60": "z_turnover_60",
  "rs_acceleration_zscore_topix": "rs_acceleration_zscore",
  "rs_acceleration_zscore_nikkei": "rs_acceleration_zscore",
  "rs_acceleration_topix": "rs_acceleration",
  "rs_acceleration_nikkei": "rs_acceleration",
  "rs31_topix": "rs31",
  "rs31_nikkei": "rs31",
  "rs63_topix": "rs63",
  "rs63_nikkei": "rs63",
  "rs126_topix": "rs126",
  "rs126_nikkei": "rs126",
  "rs252_topix": "rs252",
  "rs252_nikkei": "rs252",
  "rs_sma75_topix": "rs_sma75",
  "rs_sma75_nikkei": "rs_sma75",
  "event_news_bundle": "event_news_bundle",
  "research_prompt_block": "research_prompt_block",
  "beta_adjusted_rs_topix": "beta_adjusted_rs",
  "beta_adjusted_rs_nikkei": "beta_adjusted_rs",
  "information_ratio_topix": "information_ratio",
  "information_ratio_nikkei": "information_ratio",
  "perfect_order_days": "perfect_order_days",
  "price_change_pct": "price_change_pct",
  "turnover_ma_ratio_60": "turnover_ma_ratio_60",
  "committed_at_utc": "committed_at",
  "link_kabutan": "web_overview",
  "link_kabutan_chart": "web_chart",
  "link_kabutan_news": "web_news"
};
  const SERIES_LABEL_IDS = {
  "z_disp": "z_turnover_60",
  "rs31": "rs31",
  "rs63": "rs63",
  "rs126": "rs126",
  "rs252": "rs252",
  "rs_sma75": "rs_sma75"
};

  function columnLabelId(key) {
    if (COLUMN_LABEL_IDS[key]) return COLUMN_LABEL_IDS[key];
    const base = String(key || "").replace(/_(topix|nikkei)$/, "");
    return COLUMN_LABEL_IDS[base] || "";
  }

  function attachLabelTip(el, id) {
    if (el && id && LABEL_TIPS[id]) el.dataset.labelTip = id;
  }

  function labelTipText(id) {
    const entry = LABEL_TIPS[id];
    if (!entry) return "";
    const parts = [];
    if (entry.family) parts.push(LABEL_FAMILY_INDEX);
    if (entry.text) parts.push(entry.text);
    return parts.join("\n\n");
  }

  function bindLabelTips() {
    if (document.getElementById("label-tip")) return;
    const tip = document.createElement("div");
    tip.id = "label-tip";
    tip.hidden = true;
    tip.setAttribute("role", "tooltip");
    document.body.appendChild(tip);
    let current = null;
    function hide() {
      current = null;
      tip.hidden = true;
    }
    function show(host) {
      if (!host || host.closest(".surface-chrome-source, .surface-header-source")) return;
      const text = labelTipText(host.dataset.labelTip || "");
      if (!text) return;
      current = host;
      tip.textContent = text;
      tip.hidden = false;
      const rect = host.getBoundingClientRect();
      const width = tip.offsetWidth;
      const height = tip.offsetHeight;
      let left = Math.min(rect.left, window.innerWidth - width - 8);
      left = Math.max(8, left);
      let top = rect.bottom + 8;
      if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 8);
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }
    document.addEventListener("mouseover", (ev) => {
      const host = ev.target.closest ? ev.target.closest("[data-label-tip]") : null;
      if (!host) return;
      show(host);
    });
    document.addEventListener("mouseout", (ev) => {
      const host = ev.target.closest ? ev.target.closest("[data-label-tip]") : null;
      if (!host || host !== current) return;
      const next = ev.relatedTarget;
      if (next && host.contains(next)) return;
      hide();
    });
    document.addEventListener("focusin", (ev) => {
      const host = ev.target.closest ? ev.target.closest("[data-label-tip]") : null;
      if (host) show(host);
    });
    document.addEventListener("focusout", (ev) => {
      const host = ev.target.closest ? ev.target.closest("[data-label-tip]") : null;
      if (host) hide();
    });
  }

  function seriesDisplayMeta() {
    const head = [];
    const rs = [];
    SERIES_META.forEach((s) => {
      if (s.id === "z_disp") head.push(s);
      else rs.push(s);
    });
    return head.concat(rs.reverse());
  }

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
    favLists: [],
    favFilterIds: [],
    favIncludeBlank: true,
    favModalListId: null,
    favOnly: false,
    excludeAllRsNeg: false,
    sortKey: "z_turnover_60",
    sortDir: "desc",
    colFilters: {},
    filterMenuKey: null,
    tabSettings: null,
    prefsVisibleKeys: null,
    prefsDefaultKeysSnapshot: null,
    visibleKeysReady: false,
    prevAllKeys: [],
    selected: null,
    hovered: null,
    seriesCache: {},
    visibleChartCodes: [],
    chartBuildId: 0,
    chartObserver: null,
    kabutanMode: "overview",
    kabutanTimer: null,
    rowObserver: null,
    dataUpdatedAt: null,
    seenBundleKey: "",
    bundleNotice: null,
  };

  const $ = (id) => document.getElementById(id);
  const chrome = () => window.StockRadarChrome;
  let lastFavAnchor = null;
  const FAV_LIST_MAX = 12;
  const FAV_CELL_CHIPS = 5;
  const FAV_NAME_MAX = 20;
  const FAV_LIST_CAP_PLACEHOLDER = "最大数に達しています";
  const FAV_CODES_PER_LIST = 500;
  const FAV_MEMBERSHIP_MAX = 1500;
  const FAV_DEFAULT_ID = "lst_default";
  const FAV_HUES = ["#4da5ee", "#e8b44a", "#57bb8a", "#e07a5f", "#9b8cff", "#d47bb0"];

  const COPY = {
    login: "ログインしてください",
    unavailable: "利用できません",
    temporary: "一時的に利用できません",
  };
  const UNSUFFIXED = [
    "rs_acceleration",
    "rs_acceleration_zscore",
    "rs31",
    "rs63",
    "rs126",
    "rs252",
    "rs_sma75",
    "beta_adjusted_rs",
    "information_ratio",
  ];
  let prefsTimer = null;
  let viewRefreshQueued = false;

  function liveCtx() {
    return window.__WEB_UI_CTX || null;
  }

  function bootProgress(label, ratio) {
    const p = window.__webUiProgress;
    if (p && typeof p.show === "function") p.show(label, ratio);
  }

  function hideBootProgress() {
    const p = window.__webUiProgress;
    if (p && typeof p.hide === "function") p.hide();
  }

  function showT5(kind, text) {
    hideBootProgress();
    const msg = text || COPY[kind] || COPY.temporary;
    const banner = $("asof-banner");
    if (banner) banner.textContent = msg;
    const overlay = $("t5-overlay");
    if (overlay) {
      overlay.hidden = false;
      overlay.className = "t5-overlay t5-" + kind;
      overlay.textContent = msg;
    }
    if (kind === "login") {
      const login = $("login-shell");
      const app = $("app-root");
      if (login) login.hidden = false;
      if (app) app.hidden = true;
    }
  }

  async function bffSend(origin, path, init, token) {
    try {
      return await fetch(String(origin).replace(/\/$/, "") + path, {
        ...(init || {}),
        headers: {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
          ...((init && init.headers) || {}),
        },
      });
    } catch (_err) {
      return null;
    }
  }

  async function bffFetch(path, init) {
    const ctx = liveCtx();
    if (!ctx || !ctx.bffOrigin) {
      const err = new Error("login");
      err.t5 = "login";
      throw err;
    }
    let token = ctx.accessToken || "";
    if (typeof window.__webUiFreshAccessToken === "function") {
      try {
        const fresh = await window.__webUiFreshAccessToken();
        if (fresh) token = fresh;
      } catch (_err) {
        /* use the snapshot already copied into the session */
      }
    }
    if (!token) {
      const err = new Error("login");
      err.t5 = "login";
      throw err;
    }
    let res = await bffSend(ctx.bffOrigin, path, init, token);
    if (!res) {
      const err = new Error("temporary");
      err.t5 = "temporary";
      throw err;
    }
    if (res.status === 401 && typeof window.__webUiFreshAccessToken === "function") {
      let fresh = null;
      try {
        fresh = await window.__webUiFreshAccessToken(true);
      } catch (_err) {
        fresh = null;
      }
      if (fresh && fresh !== token) {
        res = await bffSend(ctx.bffOrigin, path, init, fresh);
        if (!res) {
          const err = new Error("temporary");
          err.t5 = "temporary";
          throw err;
        }
      }
    }
    if (res.status === 401) {
      const err = new Error("login");
      err.t5 = "login";
      throw err;
    }
    if (res.status === 403) {
      const err = new Error("unavailable");
      err.t5 = "unavailable";
      throw err;
    }
    if (!res.ok) {
      const err = new Error("temporary");
      err.t5 = "temporary";
      throw err;
    }
    return res.json();
  }

  async function gunzipJson(buf) {
    const ds = new DecompressionStream("gzip");
    const stream = new Blob([buf]).stream().pipeThrough(ds);
    const text = await new Response(stream).text();
    return JSON.parse(text);
  }

  function aliasBundle(bundle) {
    const bench = bundle.benchmark;
    const suffix = bench === "nikkei" ? "_nikkei" : "_topix";
    const rows = (bundle.rows || []).map((row) => {
      const out = { ...row };
      for (const k of UNSUFFIXED) {
        if (Object.prototype.hasOwnProperty.call(out, k)) out[k + suffix] = out[k];
      }
      return out;
    });
    const series = {};
    for (const [code, metrics] of Object.entries(bundle.series || {})) {
      const values = { ...(metrics || {}) };
      for (const k of UNSUFFIXED) {
        if (metrics && metrics[k]) values[k + suffix] = metrics[k];
      }
      series[code] = { values };
    }
    return {
      rows,
      series,
      bench,
      as_of: bundle.as_of,
      axis_dates: bundle.axis_dates,
      n_rows: rows.length,
      csv_source: bundle.csv_source || "",
    };
  }

  async function decodeBundleBuffer(buf) {
    const bytes = new Uint8Array(buf);
    const gzipMagic = bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
    if (gzipMagic) return gunzipJson(buf);
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  async function readBodyWithProgress(res, onBytes) {
    const total = Number(res.headers.get("content-length") || 0);
    if (!res.body || typeof res.body.getReader !== "function") {
      const buf = await res.arrayBuffer();
      if (onBytes) onBytes(buf.byteLength, total || buf.byteLength);
      return buf;
    }
    const reader = res.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.byteLength;
      if (onBytes) onBytes(received, total);
    }
    const out = new Uint8Array(received);
    let offset = 0;
    for (const chunk of chunks) {
      out.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return out.buffer;
  }

  async function loadBundle(asOf, bench) {
    bootProgress("署名付きURLを発行しています", 0.62);
    const minted = await bffFetch("/v1/mint", {
      method: "POST",
      body: JSON.stringify({ as_of: asOf, benchmark: bench }),
    });
    const url = minted && minted.signed_url;
    if (!url) {
      const err = new Error("temporary");
      err.t5 = "temporary";
      throw err;
    }
    let res;
    try {
      bootProgress("束をダウンロードしています", 0.68);
      res = await fetch(url, { cache: "no-store" });
    } catch (_err) {
      const err = new Error("temporary");
      err.t5 = "temporary";
      throw err;
    }
    if (!res.ok) {
      const err = new Error("temporary");
      err.t5 = "temporary";
      throw err;
    }
    state.dataUpdatedAt = minted.committed_at_utc || res.headers.get("last-modified") || null;
    const buf = await readBodyWithProgress(res, (got, total) => {
      if (total > 0) {
        bootProgress("束をダウンロードしています", 0.68 + 0.22 * (got / total));
      } else {
        bootProgress("束をダウンロードしています", 0.78);
      }
    });
    bootProgress("束を展開しています", 0.92);
    const bundle = await decodeBundleBuffer(buf);
    return aliasBundle(bundle);
  }

  function schedulePrefsSave() {
    clearTimeout(prefsTimer);
    prefsTimer = setTimeout(() => {
      pushPrefs().catch(() => {});
    }, 400);
  }

  function setViewBusy(on) {
    const el = $("view-busy");
    const host = $("workspace") || document.querySelector("main.layout");
    if (el) el.hidden = !on;
    if (host) {
      if (on) host.setAttribute("aria-busy", "true");
      else host.removeAttribute("aria-busy");
    }
  }

  function requestViewRefresh(opts) {
    state.pendingViewRefreshOpts = opts || {};
    setViewBusy(true);
    if (viewRefreshQueued) return;
    viewRefreshQueued = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        viewRefreshQueued = false;
        try {
          renderTable(state.pendingViewRefreshOpts || {});
        } finally {
          if (!viewRefreshQueued) setViewBusy(false);
        }
      });
    });
  }

  function sameCodeList(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  async function pushPrefs() {
    const bag = {
      favorites: {
        lists: state.favLists.map((list) => ({
          id: list.id,
          name: list.name,
          hue: list.hue,
          codes: list.codes.slice().sort(),
        })),
        codes: unionFavCodes(),
        filter_ids: state.favFilterIds.slice(),
        include_blank: !!state.favIncludeBlank,
      },
      display: {
        bench: state.bench,
        favOnly: state.favOnly,
        excludeAllRsNeg: state.excludeAllRsNeg,
        visibleKeys: state.visibleKeys,
        defaultKeysSnapshot: Array.isArray(state.prefsDefaultKeysSnapshot)
          ? state.prefsDefaultKeysSnapshot
          : state.visibleKeys,
        tabSettings: state.tabSettings,
        sortKey: state.sortKey,
        sortDir: state.sortDir,
        colFilters: state.colFilters,
      },
    };
    await bffFetch("/v1/preferences", {
      method: "PATCH",
      body: JSON.stringify({ bag }),
    });
  }

  async function applyPrefsBag(bag) {
    const next = bag && typeof bag === "object" ? bag : {};
    state.favLists = normalizeFavLists(next.favorites);
    rebuildFavIndex();
    const rawFilter = next.favorites && Array.isArray(next.favorites.filter_ids) ? next.favorites.filter_ids : [];
    const known = {};
    state.favLists.forEach((list) => { known[list.id] = true; });
    state.favFilterIds = rawFilter.map((id) => String(id)).filter((id) => known[id] || id === "__none__");
    if (!state.favLists.some((list) => list.id === state.favModalListId)) {
      state.favModalListId = state.favLists[0] ? state.favLists[0].id : null;
    }
    const display = next.display && typeof next.display === "object" ? next.display : {};
    if (display.bench === "topix" || display.bench === "nikkei") state.bench = display.bench;
    if (typeof display.favOnly === "boolean") state.favOnly = display.favOnly;
    if (next.favorites && typeof next.favorites.include_blank === "boolean") {
      state.favIncludeBlank = next.favorites.include_blank;
    } else {
      state.favIncludeBlank = !state.favOnly;
    }
    if (typeof display.excludeAllRsNeg === "boolean") state.excludeAllRsNeg = display.excludeAllRsNeg;
    if (Array.isArray(display.visibleKeys) && display.visibleKeys.length) {
      state.prefsVisibleKeys = display.visibleKeys.slice();
    }
    if (Array.isArray(display.defaultKeysSnapshot)) {
      state.prefsDefaultKeysSnapshot = display.defaultKeysSnapshot.slice();
    }
    if (display.tabSettings && typeof display.tabSettings === "object") {
      state.tabSettings = { ...TAB_SETTINGS_DEFAULT, ...display.tabSettings };
    }
    if (display.colFilters && typeof display.colFilters === "object") state.colFilters = display.colFilters;
    if (typeof display.sortKey === "string") state.sortKey = display.sortKey;
    if (display.sortDir === "asc" || display.sortDir === "desc") state.sortDir = display.sortDir;
    const benchSel = $("bench-mode");
    if (benchSel) benchSel.value = state.bench;
    if ($("filter-exclude-all-rs-neg")) $("filter-exclude-all-rs-neg").checked = state.excludeAllRsNeg;
  }



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
    beta_adjusted_rs_topix: { key: "beta_adjusted_rs_topix", label: "除β 252日RS", kind: "signed1", bench: true },
    information_ratio_topix: { key: "information_ratio_topix", label: "RSの安定度", kind: "signed1", bench: true },
    perfect_order_days: { key: "perfect_order_days", label: "ﾊﾟｰﾌｪｸﾄｵｰﾀﾞｰ日数", kind: "int" },
    price_change_pct: { key: "price_change_pct", label: "前日比(%)", kind: "signed1" },
    turnover_ma_ratio_60: { key: "turnover_ma_ratio_60", label: "売買代金倍率", kind: "signed1" },
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
    if (UNSUFFIXED.includes(k)) return true;
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


  function padFavCode(code) {
    return String(code == null ? "" : code).padStart(4, "0");
  }

  function uniqueFavCodes(arr) {
    const out = [];
    const seen = {};
    (Array.isArray(arr) ? arr : []).forEach((item) => {
      const code = padFavCode(item);
      if (!code || code === "0000" || seen[code]) return;
      seen[code] = true;
      out.push(code);
    });
    return out.slice(0, FAV_CODES_PER_LIST);
  }

  function defaultFavList(codes) {
    return { id: FAV_DEFAULT_ID, name: "お気入り", hue: 0, codes: uniqueFavCodes(codes) };
  }

  function normalizeFavLists(fav) {
    const bag = fav && typeof fav === "object" ? fav : {};
    const rawLists = Array.isArray(bag.lists) ? bag.lists : null;
    if (!rawLists || !rawLists.length) {
      return [defaultFavList(Array.isArray(bag.codes) ? bag.codes : [])];
    }
    const seenId = {};
    const out = [];
    rawLists.forEach((raw, index) => {
      if (!raw || typeof raw !== "object" || out.length >= FAV_LIST_MAX) return;
      let id = String(raw.id || "").trim();
      if (!id || seenId[id]) id = "lst_" + String(index + 1).padStart(2, "0");
      seenId[id] = true;
      let name = String(raw.name || "").trim().slice(0, FAV_NAME_MAX);
      if (!name) name = "リスト" + (out.length + 1);
      let hue = Number(raw.hue);
      if (!Number.isInteger(hue) || hue < 0 || hue > 5) hue = out.length % 6;
      out.push({ id, name, hue, codes: uniqueFavCodes(raw.codes) });
    });
    return out.length ? out : [defaultFavList([])];
  }

  function unionFavCodes() {
    const seen = {};
    const out = [];
    state.favLists.forEach((list) => {
      list.codes.forEach((code) => {
        if (seen[code]) return;
        seen[code] = true;
        out.push(code);
      });
    });
    return out.sort();
  }

  function rebuildFavIndex() {
    const mapped = {};
    unionFavCodes().forEach((code) => { mapped[code] = true; });
    state.favorites = mapped;
  }

  function favHueColor(hue) {
    return FAV_HUES[Math.max(0, Number(hue) || 0) % FAV_HUES.length];
  }

  function nextFavHue() {
    const used = {};
    state.favLists.forEach((list) => { used[list.hue] = true; });
    for (let i = 0; i < FAV_HUES.length; i++) {
      if (!used[i]) return i;
    }
    return state.favLists.length % FAV_HUES.length;
  }

  function nextFavListId() {
    const seen = {};
    state.favLists.forEach((list) => { seen[list.id] = true; });
    for (let i = 0; i < 40; i++) {
      const id = "lst_" + Math.random().toString(36).slice(2, 10);
      if (!seen[id]) return id;
    }
    return "lst_" + String(Date.now()).slice(-8);
  }

  function findFavList(id) {
    return state.favLists.find((list) => list.id === id) || null;
  }

  function isFavorite(code) {
    return !!state.favorites[padFavCode(code)];
  }

  function codeInFavList(list, code) {
    return !!(list && list.codes.indexOf(padFavCode(code)) >= 0);
  }

  function listsForCode(code) {
    const c = padFavCode(code);
    return state.favLists.filter((list) => list.codes.indexOf(c) >= 0);
  }

  function favMembershipCount() {
    return state.favLists.reduce((n, list) => n + list.codes.length, 0);
  }

  function persistFavLists(opts) {
    opts = opts || {};
    rebuildFavIndex();
    schedulePrefsSave();
    // Table rows are rebuilt by requestViewRefresh. Chart cards keep their
    // fav-star nodes, so the same patch has to run either way.
    if (opts.refresh || state.favOnly) requestViewRefresh();
    patchFavCell(opts.code);
    const modal = $("fav-lists-modal");
    if (opts.modal && modal && !modal.classList.contains("hidden")) renderFavListsModal();
    if (opts.flyoutCode) refreshFavFlyout(opts.flyoutCode);
  }

  function patchFavCell(code) {
    const sel = code
      ? 'button.fav-star[data-fav-code="' + padFavCode(code) + '"]'
      : "button.fav-star";
    document.querySelectorAll(sel).forEach((btn) => {
      const c = btn.dataset.favCode;
      const html = favCellInnerHtml(c);
      if (btn.innerHTML !== html) btn.innerHTML = html;
      const on = isFavorite(c);
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function toggleCodeInFavList(code, listId) {
    if (state.freePreview) return;
    const list = findFavList(listId);
    if (!list) return;
    const c = padFavCode(code);
    const at = list.codes.indexOf(c);
    if (at >= 0) {
      list.codes.splice(at, 1);
    } else {
      if (list.codes.length >= FAV_CODES_PER_LIST) return;
      if (favMembershipCount() >= FAV_MEMBERSHIP_MAX) return;
      list.codes.push(c);
    }
    persistFavLists({ code: c, flyoutCode: c, modal: true });
  }

  function favCodeAddAtCap(list) {
    return !list || list.codes.length >= FAV_CODES_PER_LIST || favMembershipCount() >= FAV_MEMBERSHIP_MAX;
  }

  function syncFavCreateFields(input, addBtn, idlePlaceholder, atCap) {
    if (atCap == null) atCap = state.favLists.length >= FAV_LIST_MAX;
    if (addBtn) addBtn.disabled = atCap;
    if (!input) return;
    input.disabled = atCap;
    if (atCap) input.value = "";
    input.placeholder = atCap ? FAV_LIST_CAP_PLACEHOLDER : idlePlaceholder;
    input.title = atCap ? FAV_LIST_CAP_PLACEHOLDER : "";
  }

  function createFavList(name, initialCode) {
    if (state.freePreview || state.favLists.length >= FAV_LIST_MAX) return null;
    const trimmed = String(name || "").trim().slice(0, FAV_NAME_MAX);
    const list = {
      id: nextFavListId(),
      name: trimmed || ("リスト" + (state.favLists.length + 1)),
      hue: nextFavHue(),
      codes: initialCode ? uniqueFavCodes([initialCode]) : [],
    };
    state.favLists.push(list);
    if (!state.favModalListId) state.favModalListId = list.id;
    persistFavLists({ code: initialCode, flyoutCode: initialCode, modal: true, refresh: true });
    return list;
  }

  function renameFavList(listId, name) {
    const list = findFavList(listId);
    if (!list || state.freePreview) return;
    const trimmed = String(name || "").trim().slice(0, FAV_NAME_MAX);
    if (!trimmed) return;
    list.name = trimmed;
    persistFavLists({ modal: true });
  }

  function deleteFavList(listId) {
    if (state.freePreview || state.favLists.length <= 1) return;
    state.favLists = state.favLists.filter((list) => list.id !== listId);
    state.favFilterIds = state.favFilterIds.filter((id) => id !== listId);
    if (state.favModalListId === listId) {
      state.favModalListId = state.favLists[0] ? state.favLists[0].id : null;
    }
    persistFavLists({ refresh: true, modal: true });
  }

  function reorderFavLists(ids) {
    const next = ids.map((id) => findFavList(id)).filter(Boolean);
    if (next.length !== state.favLists.length) return;
    let changed = false;
    for (let i = 0; i < next.length; i++) {
      if (next[i].id !== state.favLists[i].id) {
        changed = true;
        break;
      }
    }
    if (!changed) return;
    state.favLists = next;
    persistFavLists({ refresh: true, modal: true });
  }

  function favRenameFocused() {
    const el = $("fav-list-rename");
    if (!el) return false;
    const active = document.activeElement;
    return active === el || el.contains(active) || !!(el.shadowRoot && el.shadowRoot.activeElement);
  }

  function commitFavListRename() {
    const el = $("fav-list-rename");
    const list = findFavList(state.favModalListId);
    if (!el || !list || state.freePreview) return;
    const next = String(el.value || "").trim().slice(0, FAV_NAME_MAX);
    if (!next) {
      el.value = list.name;
      return;
    }
    if (next !== list.name) renameFavList(list.id, next);
  }

  function placeFavDragRow(nav, moving, clientY) {
    const rows = [...nav.querySelectorAll(".fav-list-row")].filter((el) => el !== moving);
    const before = rows.find((el) => {
      const box = el.getBoundingClientRect();
      return clientY < box.top + box.height / 2;
    });
    if (before) nav.insertBefore(moving, before);
    else nav.appendChild(moving);
  }

  function commitFavNavOrder(nav) {
    if (!nav) return;
    reorderFavLists([...nav.querySelectorAll(".fav-list-row")].map((el) => el.dataset.listId));
  }

  let favDragViaHtml5 = false;

  function bindFavListDrag(handle, row, listId) {
    handle.draggable = true;
    handle.addEventListener("dragstart", (ev) => {
      favDragViaHtml5 = true;
      row.classList.add("is-dragging");
      ev.dataTransfer.effectAllowed = "move";
      try {
        ev.dataTransfer.setData("text/plain", listId);
      } catch (_) {}
    });
    handle.addEventListener("dragend", () => {
      row.classList.remove("is-dragging");
      favDragViaHtml5 = false;
      commitFavNavOrder($("fav-lists-nav"));
    });
    handle.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      ev.stopPropagation();
      const nav = $("fav-lists-nav");
      if (!nav) return;
      try {
        handle.setPointerCapture(ev.pointerId);
      } catch (_) {}
      let dragging = false;
      const startY = ev.clientY;
      const onMove = (moveEv) => {
        if (Math.abs(moveEv.clientY - startY) < 4 && !dragging) return;
        dragging = true;
        row.classList.add("is-dragging");
        placeFavDragRow(nav, row, moveEv.clientY);
      };
      const onUp = () => {
        try {
          handle.releasePointerCapture(ev.pointerId);
        } catch (_) {}
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        if (favDragViaHtml5) return;
        row.classList.remove("is-dragging");
        if (!dragging) {
          if (state.favModalListId !== listId) {
            state.favModalListId = listId;
            renderFavListsModal();
          }
          return;
        }
        commitFavNavOrder(nav);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  function addCodeToFavList(listId, code) {
    const list = findFavList(listId);
    const c = padFavCode(toHalfWidthCode(code));
    if (!list || !c || c.length < 4) return false;
    if (list.codes.indexOf(c) >= 0) return true;
    if (list.codes.length >= FAV_CODES_PER_LIST || favMembershipCount() >= FAV_MEMBERSHIP_MAX) return false;
    list.codes.push(c);
    persistFavLists({ code: c, refresh: true, modal: true });
    return true;
  }

  function removeCodeFromFavList(listId, code) {
    const list = findFavList(listId);
    if (!list) return;
    const c = padFavCode(code);
    list.codes = list.codes.filter((item) => item !== c);
    persistFavLists({ code: c, refresh: true, modal: true });
  }

  function favCellInnerHtml(code) {
    const lists = listsForCode(code);
    if (!lists.length) return '<span class="fav-empty" aria-hidden="true"></span>';
    const shown = lists.slice(0, FAV_CELL_CHIPS);
    const extra = lists.length - shown.length;
    return (
      shown
        .map((list) =>
          '<span class="fav-chip" style="background:' +
          favHueColor(list.hue) +
          '" title="' +
          escapeHtml(list.name) +
          '"></span>'
        )
        .join("") +
      (extra > 0 ? '<span class="fav-more">+' + extra + "</span>" : "")
    );
  }

  function closeFavFlyout() {
    blurTextFieldInside(".fav-flyout");
    document.querySelectorAll(".fav-flyout").forEach((el) => el.remove());
  }

  function refreshFavFlyout(code) {
    const menu = document.querySelector(".fav-flyout");
    if (!menu || menu.dataset.favCode !== padFavCode(code)) return;
    const c = padFavCode(code);
    let anchor = lastFavAnchor;
    if (!anchor || !anchor.isConnected || !anchor.dataset || anchor.dataset.favCode !== c) {
      anchor = document.querySelector('button.fav-star[data-fav-code="' + c + '"]');
    }
    if (anchor) openFavFlyout(anchor, code);
  }

  function openFavFlyout(anchor, code) {
    closeFavFlyout();
    closeFilterMenu();
    if (state.freePreview || !anchor) return;
    const c = padFavCode(code);
    lastFavAnchor = anchor;
    const menu = document.createElement("div");
    menu.className = "fav-flyout";
    menu.dataset.favCode = c;
    menu.addEventListener("click", (ev) => ev.stopPropagation());
    state.favLists.forEach((list) => {
      const inList = codeInFavList(list, c);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = inList ? "in" : "";
      btn.innerHTML =
        '<span class="fav-chip" style="background:' +
        favHueColor(list.hue) +
        '"></span><span>' +
        escapeHtml(list.name) +
        '</span><span class="fav-flyout-check">' +
        (inList ? "✓" : "") +
        "</span>";
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        toggleCodeInFavList(c, list.id);
      });
      menu.appendChild(btn);
    });
    const create = document.createElement("div");
    create.className = "fav-flyout-create";
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = FAV_NAME_MAX;
    markNonCredentialInput(input, "list-label");
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.textContent = "追加";
    syncFavCreateFields(input, addBtn, "新しいリスト");
    const onCreate = () => {
      if (addBtn.disabled) return;
      const created = createFavList(input.value, c);
      if (created) input.value = "";
    };
    addBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      onCreate();
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        onCreate();
      }
    });
    create.appendChild(input);
    create.appendChild(addBtn);
    menu.appendChild(create);
    document.body.appendChild(menu);
    const rect = anchor.getBoundingClientRect();
    const mw = Math.max(220, menu.offsetWidth);
    let left = rect.left;
    if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8);
    menu.style.left = left + "px";
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8) + "px";
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

  function isTextFilterCol(key) {
    return key === "code" || key === "name";
  }

  function toHalfWidthCode(value) {
    const half = String(value == null ? "" : value).replace(/[\uFF01-\uFF5E]/g, (ch) =>
      String.fromCharCode(ch.charCodeAt(0) - 0xFEE0)
    );
    return half.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
  }

  const CORE_UNIVERSE_TIP = "この画面が扱う銘柄の範囲。国内株式のうち、上場して間もない銘柄（約1年分の株価がまだない）と、 売買代金が少なく取引が薄い銘柄を除いたもの。画面の数値はすべてこの範囲の中で計算している。";

  function coreUniverseTermHtml() {
    return (
      '<button type="button" class="core-universe-term" aria-label="対象銘柄の説明">' +
      "対象銘柄" +
      '<span class="core-universe-tip" role="tooltip">' +
      escapeHtml(CORE_UNIVERSE_TIP) +
      "</span>" +
      "</button>"
    );
  }

  function unknownTickerHtml() {
    return "存在しないか、この画面の" + coreUniverseTermHtml() + "に含まれません";
  }

  function coreHasCodeQuery(q) {
    const needle = toHalfWidthCode(q);
    if (!needle) return false;
    return state.rows.some((row) => toHalfWidthCode(row.code).includes(needle));
  }

  function coreHasNameQuery(q) {
    const needle = String(q || "").trim().toLowerCase();
    if (!needle) return false;
    return state.rows.some((row) => String(row.name || "").toLowerCase().includes(needle));
  }

  function describeCodeMiss(raw) {
    const needle = toHalfWidthCode(raw);
    if (!needle) return "";
    if (coreHasCodeQuery(needle)) return coreUniverseTermHtml() + "にありますが、他のフィルタで表示されていません。";
    return unknownTickerHtml();
  }

  function searchMissMessage() {
    const codeFilt = state.colFilters.code;
    const nameFilt = state.colFilters.name;
    const codeQ = codeFilt && codeFilt.op === "contains" ? String(codeFilt.q || "") : "";
    const nameQ = nameFilt && nameFilt.op === "contains" ? String(nameFilt.q || "").trim() : "";
    if (!codeQ && !nameQ) return "";
    if (codeQ) return describeCodeMiss(codeQ);
    if (coreHasNameQuery(nameQ)) return coreUniverseTermHtml() + "にありますが、他のフィルタで表示されていません。";
    return unknownTickerHtml();
  }

  function favAddCodeHint(raw) {
    const needle = toHalfWidthCode(raw);
    if (!needle || needle.length < 4) return "";
    if (findRowByCode(padFavCode(needle))) return "";
    return describeCodeMiss(needle);
  }

  function writeMissHtml(el, html) {
    if (!el) return;
    el.innerHTML = html || "";
    el.hidden = !html;
  }

  function updateSearchMiss(rowCount) {
    const el = $("search-miss");
    if (!el) return;
    writeMissHtml(el, rowCount === 0 ? searchMissMessage() : "");
  }

  function updateFavAddCodeHint() {
    const el = $("fav-list-add-code-hint");
    const input = $("fav-list-add-code");
    if (!el) return;
    const html = input && !input.disabled ? favAddCodeHint(input.value) : "";
    writeMissHtml(el, html);
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
    if (filt.op === "contains") {
      const q = String(filt.q == null ? "" : filt.q).trim();
      if (!q) return true;
      const cell = raw == null ? "" : String(raw);
      if (baseKey === "code") {
        const needle = toHalfWidthCode(q);
        if (!needle) return true;
        return toHalfWidthCode(cell).includes(needle);
      }
      return cell.toLowerCase().includes(q.toLowerCase());
    }
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
    blurTextFieldInside(".col-filter-menu, .fav-filter-anchor, wa-dropdown.fav-filter-dropdown");
    state.filterMenuKey = null;
    document.querySelectorAll(".col-filter-menu, .fav-filter-anchor, wa-dropdown.fav-filter-dropdown").forEach((el) => el.remove());
    closeFavFlyout();
  }

  function closeAccountMenu() {
    const dropdown = $("account-dropdown");
    if (dropdown) dropdown.open = false;
  }

  let confirmPending = null;

  function confirmDialogReady() {
    return typeof customElements !== "undefined" && customElements.get("wa-dialog") && $("confirm-dialog");
  }

  function bindConfirmDialog() {
    const dialog = $("confirm-dialog");
    const ok = $("confirm-dialog-ok");
    const cancel = $("confirm-dialog-cancel");
    if (!dialog || dialog.dataset.bound === "1") return;
    dialog.dataset.bound = "1";
    const settle = (accepted) => {
      const fn = confirmPending;
      confirmPending = null;
      if (dialog.open) dialog.open = false;
      if (accepted && typeof fn === "function") fn();
    };
    if (ok) {
      ok.addEventListener("click", (ev) => {
        ev.preventDefault();
        settle(true);
      });
    }
    if (cancel) {
      cancel.addEventListener("click", (ev) => {
        ev.preventDefault();
        settle(false);
      });
    }
    dialog.addEventListener("wa-hide", () => {
      confirmPending = null;
    });
  }

  function confirmDestructive(message, onOk, okLabel) {
    bindConfirmDialog();
    const dialog = $("confirm-dialog");
    const body = $("confirm-dialog-body");
    const ok = $("confirm-dialog-ok");
    if (!confirmDialogReady()) {
      if (window.confirm(message)) onOk();
      return;
    }
    if (body) body.textContent = message;
    if (ok) ok.textContent = okLabel || "削除";
    confirmPending = onOk;
    dialog.open = true;
  }

  function bindAccountMenu() {
    const dropdown = $("account-dropdown");
    if (!dropdown || dropdown.dataset.bound === "1") return;
    dropdown.dataset.bound = "1";
    dropdown.addEventListener("wa-select", (ev) => {
      const item = ev.detail && ev.detail.item;
      const value = item ? String(item.value || "") : "";
      if (value === "lists") openFavListsModal();
      if (value === "logout" && typeof window.__webUiLogout === "function") window.__webUiLogout();
    });
  }

  function openFavListsModal() {
    if (state.freePreview) return;
    closeFavFlyout();
    closeAccountMenu();
    if (!state.favLists.length) state.favLists = [defaultFavList([])];
    if (!findFavList(state.favModalListId)) {
      state.favModalListId = state.favLists[0].id;
    }
    renderFavListsModal();
    const modal = $("fav-lists-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeFavListsModal() {
    blurTextFieldInside("#fav-lists-modal");
    const modal = $("fav-lists-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  function nameLookup(code) {
    const row = findRowByCode(padFavCode(code));
    return row && row.name ? String(row.name) : "";
  }

  function renderFavListsModal() {
    const nav = $("fav-lists-nav");
    const members = $("fav-lists-members");
    const renameEl = $("fav-list-rename");
    const deleteBtn = $("fav-list-delete");
    if (!nav || !members) return;
    if (nav.dataset.favDragBound !== "1") {
      nav.dataset.favDragBound = "1";
      nav.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        const moving = nav.querySelector(".fav-list-row.is-dragging");
        if (!moving) return;
        placeFavDragRow(nav, moving, ev.clientY);
      });
    }
    nav.innerHTML = "";
    const selected = findFavList(state.favModalListId) || state.favLists[0] || null;
    state.favLists.forEach((list) => {
      const row = document.createElement("div");
      row.className = "fav-list-row" + (selected && selected.id === list.id ? " active" : "");
      row.dataset.listId = list.id;
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "fav-list-drag";
      handle.title = "ドラッグして並べ替え";
      handle.setAttribute("aria-label", "ドラッグして並べ替え");
      handle.innerHTML =
        '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M5 2.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zm6 0a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zM5 6.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zm6 0a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zM5 10.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zm6 0a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5z"/></svg>';
      bindFavListDrag(handle, row, list.id);
      const pick = document.createElement("button");
      pick.type = "button";
      pick.className = "fav-list-row-name";
      pick.innerHTML =
        '<span class="fav-chip" style="background:' +
        favHueColor(list.hue) +
        '"></span>' +
        escapeHtml(list.name) +
        ' <span class="muted">(' +
        list.codes.length +
        ")</span>";
      pick.addEventListener("click", () => {
        state.favModalListId = list.id;
        renderFavListsModal();
      });
      row.appendChild(handle);
      row.appendChild(pick);
      nav.appendChild(row);
    });
    syncFavCreateFields($("fav-list-new-name"), $("fav-list-add"), "新しいリスト名");
    syncFavCreateFields($("fav-list-add-code"), $("fav-list-add-code-btn"), "7011", favCodeAddAtCap(selected));
    updateFavAddCodeHint();
    if (renameEl && !favRenameFocused()) renameEl.value = selected ? selected.name : "";
    if (deleteBtn) deleteBtn.disabled = !selected || state.favLists.length <= 1;
    members.innerHTML = "";
    if (!selected) return;
    selected.codes.slice().sort().forEach((code) => {
      const row = document.createElement("div");
      row.className = "fav-member-row";
      const codeEl = document.createElement("code");
      codeEl.textContent = code;
      const name = document.createElement("span");
      name.className = "muted";
      name.textContent = nameLookup(code);
      const rm = document.createElement("button");
      rm.type = "button";
      rm.textContent = "外す";
      rm.addEventListener("click", () => {
        const listId = selected.id;
        const listName = selected.name;
        const memberCode = code;
        confirmDestructive(
          "「" + listName + "」から " + memberCode + " を外しますか？",
          () => removeCodeFromFavList(listId, memberCode),
          "外す",
        );
      });
      row.appendChild(codeEl);
      row.appendChild(name);
      row.appendChild(rm);
      members.appendChild(row);
    });
    if (!selected.codes.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "このリストに銘柄はありません。";
      members.appendChild(empty);
    }
  }

  function setSort(key, dir) {
    if (state.freePreview) return;
    state.sortKey = key;
    state.sortDir = dir;
    closeFilterMenu();
    schedulePrefsSave();
    requestViewRefresh();
  }

  function clearSort() {
    if (state.freePreview) return;
    state.sortKey = null;
    state.sortDir = "desc";
    closeFilterMenu();
    schedulePrefsSave();
    requestViewRefresh();
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
    schedulePrefsSave();
    requestViewRefresh();
  }

  function applyTextFilterFromMenu(key) {
    if (state.freePreview) return;
    const qEl = document.getElementById("cfm-q");
    if (!qEl) return;
    const raw = String(qEl.value || "");
    const q = key === "code" ? toHalfWidthCode(raw) : raw.trim();
    if (!q) delete state.colFilters[key];
    else state.colFilters[key] = { op: "contains", q };
    closeFilterMenu();
    schedulePrefsSave();
    requestViewRefresh();
  }

  // Chrome-family password extensions treat autocomplete=off as "use heuristics"
  // and then match id/name substrings such as "name". A neutral name plus off
  // keeps filter and favorite text fields out of that heuristic. inputmode=url
  // stays on stock-code fields only; Japanese names still need the IME.
  function markNonCredentialInput(el, fieldName) {
    if (!el) return;
    const apply = (node) => {
      if (!node || !node.setAttribute) return;
      if (node.getAttribute("autocomplete") !== "off") {
        node.autocomplete = "off";
        node.setAttribute("autocomplete", "off");
      }
      if (fieldName && node.getAttribute("name") !== fieldName) {
        node.name = fieldName;
        node.setAttribute("name", fieldName);
      }
      if (node.getAttribute("data-form-type") !== "other") node.setAttribute("data-form-type", "other");
    };
    apply(el);
    const syncInner = () => {
      const inner = el.shadowRoot && el.shadowRoot.querySelector("input, textarea");
      apply(inner);
    };
    syncInner();
    const ready = el.updateComplete;
    if (ready && typeof ready.then === "function") ready.then(syncInner);
    if (el.dataset && el.dataset.nonCredentialBound !== "1") {
      el.dataset.nonCredentialBound = "1";
      el.addEventListener("focusin", syncInner);
    }
  }

  const PASSWORD_MANAGER_FRAME_IDS = [
    "pejdijmoenmkgeppbflobdenhhabjlaj",
    "aeblfdkhhhdcdjpifhhbdiojplfjncoa",
    "nngceckbapebfimnlniiiahkandclblb",
    "hdokiejnpimakedhajhdlcegeplioahd",
  ];

  function focusedTextControl() {
    let node = document.activeElement;
    if (!node || node === document.body || node === document.documentElement) return null;
    let host = null;
    if (node.shadowRoot && node.shadowRoot.activeElement) host = node;
    while (node.shadowRoot && node.shadowRoot.activeElement) node = node.shadowRoot.activeElement;
    if (!node || (node.localName !== "input" && node.localName !== "textarea")) return null;
    const type = String(node.type || "text").toLowerCase();
    if (["checkbox", "radio", "button", "submit", "file", "hidden", "range", "color"].indexOf(type) >= 0) return null;
    return { control: node, host: host };
  }

  function isLoginEmail(found) {
    if (!found) return false;
    if (found.control && found.control.id === "email") return true;
    return !!(found.host && found.host.id === "email");
  }

  function blurTextControl(found) {
    if (!found) return;
    if (typeof found.control.blur === "function") found.control.blur();
    if (found.host && found.host !== found.control && typeof found.host.blur === "function") found.host.blur();
  }

  function removeStuckPasswordFrames() {
    if (isLoginEmail(focusedTextControl())) return;
    const frames = [];
    document.querySelectorAll("iframe").forEach((frame) => frames.push(frame));
    document.querySelectorAll("wa-input, wa-select").forEach((el) => {
      if (!el.shadowRoot) return;
      el.shadowRoot.querySelectorAll("iframe").forEach((frame) => frames.push(frame));
    });
    frames.forEach((frame) => {
      const src = String(frame.getAttribute("src") || "");
      const matched = PASSWORD_MANAGER_FRAME_IDS.some((id) => src.indexOf("chrome-extension://" + id + "/") === 0);
      if (!matched) return;
      const parent = frame.parentElement;
      frame.remove();
      if (parent && parent.childElementCount === 0 && parent !== document.body && parent !== document.documentElement) parent.remove();
    });
  }

  function blurTextFieldInside(selector) {
    const found = focusedTextControl();
    if (!found) return;
    const field = found.host || found.control;
    if (!(field.closest && field.closest(selector))) return;
    blurTextControl(found);
    removeStuckPasswordFrames();
  }

  function pointerDownKeepsTextControl(ev, found) {
    const path = typeof ev.composedPath === "function" ? ev.composedPath() : [];
    if (path.indexOf(found.control) >= 0) return true;
    if (found.host && path.indexOf(found.host) >= 0) return true;
    const field = found.host || found.control;
    const label = field.closest && field.closest("label");
    return !!(label && path.indexOf(label) >= 0);
  }

  // Clicks on non-focusable surface, and controls that cancel mousedown, leave
  // the inner input focused. Password UI then stays up because it never sees blur.
  function scheduleReleaseTextFieldFocus(ev) {
    const found = focusedTextControl();
    if (!found || pointerDownKeepsTextControl(ev, found)) return;
    const control = found.control;
    const host = found.host;
    setTimeout(() => {
      const now = focusedTextControl();
      if (now && now.control !== control) {
        if (!isLoginEmail(now)) removeStuckPasswordFrames();
        return;
      }
      blurTextControl({ control: control, host: host });
      removeStuckPasswordFrames();
    }, 0);
  }

  document.addEventListener("pointerdown", scheduleReleaseTextFieldFocus, true);

  function applyHalfWidthCodeAttrs(node) {
    if (!node) return;
    node.lang = "en";
    node.inputMode = "url";
    node.autocapitalize = "off";
    node.spellcheck = false;
    node.autocomplete = "off";
    if (node.style) node.style.imeMode = "disabled";
    if (node.classList) node.classList.add("cfm-code-input");
    if (node.setAttribute) {
      node.setAttribute("lang", "en");
      node.setAttribute("inputmode", "url");
      node.setAttribute("autocapitalize", "off");
      node.setAttribute("spellcheck", "false");
      node.setAttribute("autocomplete", "off");
    }
  }

  function bindHalfWidthCodeInput(el) {
    if (!el || el.dataset.halfWidthBound === "1") return;
    el.dataset.halfWidthBound = "1";
    el.lang = "en";
    // url is the alphanumeric sibling of a survey phone field (inputmode=tel):
    // Chromium reports it as a non-text input type, so Windows IME switches to
    // direct half-width alphanumeric when the field receives focus.
    el.inputMode = "url";
    applyHalfWidthCodeAttrs(el);
    const syncInner = () => {
      const inner = el.shadowRoot && el.shadowRoot.querySelector("input");
      applyHalfWidthCodeAttrs(inner);
    };
    syncInner();
    const ready = el.updateComplete;
    if (ready && typeof ready.then === "function") ready.then(syncInner);
    el.addEventListener("focus", syncInner, true);
    let composing = false;
    const apply = () => {
      if (composing) return;
      const next = toHalfWidthCode(el.value);
      if (el.value !== next) el.value = next;
    };
    el.addEventListener("compositionstart", () => { composing = true; });
    el.addEventListener("compositionend", () => {
      composing = false;
      apply();
    });
    el.addEventListener("input", apply);
    el.addEventListener("wa-input", apply);
  }

  function placeFilterMenu(menu, th) {
    document.body.appendChild(menu);
    const rect = th.getBoundingClientRect();
    const mw = Math.max(240, menu.offsetWidth);
    let left = rect.left;
    if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8);
    menu.style.left = left + "px";
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8) + "px";
  }

  function clearColFilter(key) {
    if (state.freePreview) return;
    delete state.colFilters[key];
    closeFilterMenu();
    schedulePrefsSave();
    requestViewRefresh();
  }

  const FAV_FILTER_ALL = "__all__";
  const FAV_FILTER_BLANK = "__blank__";

  function hasWaDropdown() {
    return typeof customElements !== "undefined" && !!customElements.get("wa-dropdown");
  }

  function favFilterableLists() {
    return state.favLists.filter((list) => list.codes && list.codes.length > 0);
  }

  function favBlankCount() {
    return state.rows.filter((row) => !isFavorite(padFavCode(row.code))).length;
  }

  function favCategorySelection() {
    const visible = favFilterableLists();
    const noneOn = state.favFilterIds.indexOf("__none__") >= 0;
    const emptyIds = !noneOn && !state.favFilterIds.length;
    // empty filter_ids + favOnly + include_blank means blank-only, not "all lists".
    const allListsOn = !noneOn && (!state.favOnly || (emptyIds && !state.favIncludeBlank));
    const blankOn = !noneOn && (!state.favOnly || !!state.favIncludeBlank);
    const ids = noneOn
      ? []
      : (allListsOn ? visible.map((list) => list.id) : state.favFilterIds.filter((id) => visible.some((list) => list.id === id)));
    return { blankOn, ids, allOn: blankOn && (allListsOn || !visible.length) };
  }

  function commitFavCategories(blankOn, ids) {
    if (state.freePreview) return;
    const visible = favFilterableLists();
    const knownIds = ids.filter((id) => visible.some((list) => list.id === id));
    const allListsOn = !visible.length || knownIds.length === visible.length;
    if (blankOn && (allListsOn || !state.favLists.length)) {
      state.favOnly = false;
      state.favFilterIds = [];
      state.favIncludeBlank = true;
    } else if (!blankOn && !knownIds.length) {
      state.favOnly = true;
      state.favIncludeBlank = false;
      state.favFilterIds = ["__none__"];
    } else {
      state.favOnly = true;
      state.favIncludeBlank = !!blankOn;
      state.favFilterIds = allListsOn ? [] : knownIds;
    }
    schedulePrefsSave();
    requestViewRefresh();
  }

  function makeFavFilterItem(value, label, checked, locked, hue, count) {
    const text = count != null ? label + " (" + count + ")" : label;
    if (hasWaDropdown()) {
      const item = document.createElement("wa-dropdown-item");
      item.type = "checkbox";
      item.value = value;
      item.checked = !!checked;
      item.disabled = !!locked;
      if (hue != null) {
        const chip = document.createElement("span");
        chip.slot = "icon";
        chip.className = "fav-chip";
        chip.style.background = favHueColor(hue);
        item.appendChild(chip);
      }
      item.appendChild(document.createTextNode(text));
      return item;
    }
    const lab = document.createElement("label");
    lab.className = "cfm-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = !!checked;
    input.disabled = !!locked;
    lab.appendChild(input);
    if (hue != null) {
      const chip = document.createElement("span");
      chip.className = "fav-chip";
      chip.style.background = favHueColor(hue);
      lab.appendChild(chip);
    }
    lab.appendChild(document.createTextNode(" " + text));
    return lab;
  }

  function readFavFilterChecks(root) {
    const items = hasWaDropdown()
      ? [...root.querySelectorAll("wa-dropdown-item[type='checkbox']")]
      : [...root.querySelectorAll("input[type=checkbox]")];
    const byValue = {};
    items.forEach((el) => {
      const value = hasWaDropdown() ? String(el.value || "") : String(el.value || "");
      byValue[value] = !!el.checked;
    });
    return { items, byValue };
  }

  function writeFavFilterChecks(root, selection) {
    const { items } = readFavFilterChecks(root);
    const idSet = {};
    (selection.ids || []).forEach((id) => { idSet[id] = true; });
    items.forEach((el) => {
      const value = String(el.value || "");
      if (value === FAV_FILTER_ALL) el.checked = !!selection.allOn;
      else if (value === FAV_FILTER_BLANK) el.checked = !!selection.blankOn;
      else el.checked = !!idSet[value];
    });
  }

  function applyFavFilterChecks(root, toggledValue) {
    const { byValue } = readFavFilterChecks(root);
    const visible = favFilterableLists();
    const blankShown = favBlankCount() > 0;
    let blankOn;
    let ids;
    if (toggledValue === FAV_FILTER_ALL) {
      const on = !!byValue[FAV_FILTER_ALL];
      blankOn = on && blankShown;
      ids = on ? visible.map((list) => list.id) : [];
    } else {
      blankOn = blankShown && !!byValue[FAV_FILTER_BLANK];
      ids = visible.map((list) => list.id).filter((id) => byValue[id]);
    }
    commitFavCategories(blankOn, ids);
    writeFavFilterChecks(root, favCategorySelection());
    requestAnimationFrame(() => {
      if (!root.isConnected) return;
      writeFavFilterChecks(root, favCategorySelection());
    });
  }

  function openFavFilterMenu(th) {
    closeFilterMenu();
    closeFavFlyout();
    state.filterMenuKey = "favorite";
    const locked = !!state.freePreview;
    const current = favCategorySelection();

    if (hasWaDropdown()) {
      const dropdown = document.createElement("wa-dropdown");
      dropdown.className = "fav-filter-dropdown";
      dropdown.placement = "bottom-start";
      dropdown.size = "xs";
      dropdown.distance = 4;
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.slot = "trigger";
      trigger.className = "fav-filter-dropdown-trigger";
      trigger.setAttribute("aria-label", "お気に入りフィルタ");
      dropdown.appendChild(trigger);
      dropdown.appendChild(makeFavFilterItem(FAV_FILTER_ALL, "（すべて）", current.allOn, locked));
      const split = document.createElement("wa-divider");
      dropdown.appendChild(split);
      const blankCount = favBlankCount();
      if (blankCount > 0) {
        dropdown.appendChild(makeFavFilterItem(FAV_FILTER_BLANK, "（空白）", current.blankOn, locked, null, blankCount));
      }
      favFilterableLists().forEach((list) => {
        dropdown.appendChild(
          makeFavFilterItem(list.id, list.name, current.ids.indexOf(list.id) >= 0, locked, list.hue, list.codes.length),
        );
      });
      dropdown.addEventListener("click", (ev) => ev.stopPropagation());
      dropdown.addEventListener("wa-select", (ev) => {
        ev.preventDefault();
        if (locked) return;
        const item = ev.detail && ev.detail.item;
        applyFavFilterChecks(dropdown, item ? String(item.value || "") : "");
      });
      const anchor = document.createElement("div");
      anchor.className = "fav-filter-anchor";
      const rect = th.getBoundingClientRect();
      anchor.style.left = rect.left + "px";
      anchor.style.top = rect.top + "px";
      anchor.style.width = Math.max(8, rect.width) + "px";
      anchor.style.height = Math.max(8, rect.height) + "px";
      dropdown.addEventListener("wa-after-hide", () => {
        if (anchor.parentNode) anchor.remove();
        if (state.filterMenuKey === "favorite") state.filterMenuKey = null;
      });
      anchor.appendChild(dropdown);
      document.body.appendChild(anchor);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          dropdown.open = true;
        });
      });
      return;
    }

    const menu = document.createElement("div");
    menu.className = "col-filter-menu" + (locked ? " is-locked" : "");
    menu.addEventListener("click", (ev) => ev.stopPropagation());
    if (locked) {
      const note = document.createElement("p");
      note.className = "cfm-note muted";
      note.textContent = "無料プレビュー中はお気に入りフィルタを変更できません。";
      menu.appendChild(note);
    }
    const sec = document.createElement("div");
    sec.className = "cfm-section";
    sec.appendChild(makeFavFilterItem(FAV_FILTER_ALL, "（すべて）", current.allOn, locked));
    const blankCount = favBlankCount();
    if (blankCount > 0) {
      sec.appendChild(makeFavFilterItem(FAV_FILTER_BLANK, "（空白）", current.blankOn, locked, null, blankCount));
    }
    favFilterableLists().forEach((list) => {
      sec.appendChild(makeFavFilterItem(list.id, list.name, current.ids.indexOf(list.id) >= 0, locked, list.hue, list.codes.length));
    });
    sec.querySelectorAll("input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        if (locked) return;
        applyFavFilterChecks(menu, input.value);
      });
    });
    menu.appendChild(sec);
    placeFilterMenu(menu, th);
  }

  function openTextFilterMenu(th, key) {
    closeFilterMenu();
    if (!isTextFilterCol(key)) return;
    state.filterMenuKey = key;
    const locked = !!state.freePreview;
    const menu = document.createElement("div");
    menu.className = "col-filter-menu" + (locked ? " is-locked" : "");
    menu.addEventListener("click", (ev) => ev.stopPropagation());
    const cur = state.colFilters[key] || {};
    const currentQ = cur.op === "contains" ? String(cur.q || "") : "";

    if (locked) {
      const note = document.createElement("p");
      note.className = "cfm-note muted";
      note.textContent = "無料プレビュー中はフィルタを変更できません。";
      menu.appendChild(note);
    }

    const sec = document.createElement("div");
    sec.className = "cfm-section";
    const lab = document.createElement("label");
    lab.appendChild(document.createTextNode(key === "code" ? "コード（半角英数字）" : "銘柄名"));
    const ui = chrome();
    const qEl = ui && ui.input
      ? ui.input({
          type: "text",
          placeholder: key === "code" ? "含む" : "含む",
          disabled: locked,
          value: currentQ,
          id: "cfm-q",
        })
      : document.createElement("input");
    if (!ui || !ui.input) {
      qEl.id = "cfm-q";
      qEl.type = "text";
      qEl.placeholder = "含む";
      qEl.disabled = locked;
      qEl.value = currentQ;
    }
    if (key === "code") bindHalfWidthCodeInput(qEl);
    else markNonCredentialInput(qEl, "column-filter");
    qEl.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" || locked) return;
      ev.preventDefault();
      applyTextFilterFromMenu(key);
    });
    lab.appendChild(qEl);
    sec.appendChild(lab);

    const actions = document.createElement("div");
    actions.className = "cfm-actions";
    const applyBtn = ui && ui.button ? ui.button("適用", { disabled: locked }) : document.createElement("button");
    const clearBtn = ui && ui.button ? ui.button("フィルタ清除", { disabled: locked }) : document.createElement("button");
    if (!ui || !ui.button) {
      applyBtn.type = "button";
      applyBtn.textContent = "適用";
      applyBtn.disabled = locked;
      clearBtn.type = "button";
      clearBtn.textContent = "フィルタ清除";
      clearBtn.disabled = locked;
    }
    applyBtn.addEventListener("click", () => {
      if (locked) return;
      applyTextFilterFromMenu(key);
    });
    clearBtn.addEventListener("click", () => {
      if (locked) return;
      clearColFilter(key);
    });
    actions.appendChild(applyBtn);
    actions.appendChild(clearBtn);
    sec.appendChild(actions);
    menu.appendChild(sec);
    placeFilterMenu(menu, th);
    if (!locked) {
      const focus = async () => {
        if (key === "code") qEl.inputMode = "url";
        const done = qEl.updateComplete;
        if (done && typeof done.then === "function") await done;
        try { qEl.focus(); } catch (_err) {}
      };
      focus();
    }
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
      const ui = chrome();
      const b = ui && ui.button ? ui.button(label, { disabled: locked }) : document.createElement("button");
      if (!ui || !ui.button) {
        b.type = "button";
        b.textContent = label;
        b.disabled = locked;
      }
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
      const ui = chrome();
      const clr = ui && ui.button ? ui.button("ソート解除", { disabled: locked }) : document.createElement("button");
      if (!ui || !ui.button) {
        clr.type = "button";
        clr.textContent = "ソート解除";
        clr.disabled = locked;
      }
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
    const ui = chrome();
    const sel = ui && ui.select ? ui.select() : document.createElement("select");
    sel.id = "cfm-op";
    sel.disabled = locked;
    const opItems = [
      ["none", "（なし）"],
      ["gt", "＞ より大きい"],
      ["gte", "≥ 以上"],
      ["lt", "＜ より小さい"],
      ["lte", "≤ 以下"],
      ["eq", "＝ 等しい"],
      ["between", "範囲（以下〜以上）"],
      ["notnull", "空白でない"],
      ["isnull", "空白"],
    ];
    if (ui && ui.fillSelect) {
      ui.fillSelect(sel, opItems.map(([value, text]) => ({ value, text })), cur.op || "none");
    } else {
      opItems.forEach(([v, t]) => {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = t;
        sel.appendChild(o);
      });
      sel.value = cur.op || "none";
    }
    lab.appendChild(sel);
    secFilt.appendChild(lab);

    const vals = document.createElement("div");
    vals.className = "cfm-vals";
    const aEl = ui && ui.input ? ui.input({ type: "number", placeholder: "値", disabled: locked, value: cur.a != null ? String(cur.a) : "", id: "cfm-a" }) : document.createElement("input");
    const bEl = ui && ui.input ? ui.input({ type: "number", placeholder: "上限", disabled: locked, value: cur.b != null ? String(cur.b) : "", id: "cfm-b" }) : document.createElement("input");
    if (!ui || !ui.input) {
      aEl.id = "cfm-a";
      aEl.type = "number";
      aEl.step = "any";
      aEl.placeholder = "値";
      aEl.disabled = locked;
      if (cur.a != null) aEl.value = String(cur.a);
      bEl.id = "cfm-b";
      bEl.type = "number";
      bEl.step = "any";
      bEl.placeholder = "上限";
      bEl.disabled = locked;
      if (cur.b != null) bEl.value = String(cur.b);
    }
    markNonCredentialInput(aEl, "filter-value");
    markNonCredentialInput(bEl, "filter-value");
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
    if (ui && ui.onSelectChange) ui.onSelectChange(sel, syncValVisibility);
    else sel.addEventListener("change", syncValVisibility);

    const actions = document.createElement("div");
    actions.className = "cfm-actions";
    const applyBtn = ui && ui.button ? ui.button("適用", { disabled: locked }) : document.createElement("button");
    const clearBtn = ui && ui.button ? ui.button("フィルタ清除", { disabled: locked }) : document.createElement("button");
    if (!ui || !ui.button) {
      applyBtn.type = "button";
      applyBtn.textContent = "適用";
      applyBtn.disabled = locked;
      clearBtn.type = "button";
      clearBtn.textContent = "フィルタ清除";
      clearBtn.disabled = locked;
    }
    applyBtn.addEventListener("click", () => {
      if (locked) return;
      applyColFilterFromMenu(key);
    });
    clearBtn.addEventListener("click", () => {
      if (locked) return;
      clearColFilter(key);
    });
    actions.appendChild(applyBtn);
    actions.appendChild(clearBtn);
    secFilt.appendChild(actions);
    menu.appendChild(secFilt);
    placeFilterMenu(menu, th);
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
    if (sw) {
      sw.checked = !!state.excludeAllRsNeg && !state.freePreview;
      sw.disabled = !!state.freePreview;
      sw.classList.toggle("disabled-filter", !!state.freePreview);
    }
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

  function displayPriceText(row) {
    row = row || {};
    const api = window.StockRadarPriceText;
    if (api && typeof api.displayText === "function") return api.displayText(row);
    if (row.candle_labels != null && String(row.candle_labels).trim()) {
      return api && typeof api.fromLabels === "function" ? api.fromLabels(row.candle_labels) : "";
    }
    return row.price_text == null ? "" : String(row.price_text);
  }

  function cellStyle(row, baseKey) {
    if (baseKey === "price_text") {
      const rule = priceTextCf(displayPriceText(row));
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
        rows = rows.filter((r) => {
          if (state.favFilterIds.indexOf("__none__") >= 0) return false;
          const c = padFavCode(r.code);
          const blank = !isFavorite(c);
          if (blank) return !!state.favIncludeBlank;
          if (!state.favFilterIds.length) return !state.favIncludeBlank;
          return state.favLists.some((list) =>
            state.favFilterIds.indexOf(list.id) >= 0 && codeInFavList(list, c)
          );
        });
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
    const ui = chrome();
    const keys = [...new Set([...XLSX_DEFAULT.map((c) => c.key), ...state.allKeys])]
      .filter((k) => !omitFromColsPanel(k));
    keys.forEach((k) => {
      const def = state.colDefs[k];
      const label = def ? def.label : k;
      const checked = state.visibleKeys.includes(k);
      const onToggle = (isOn) => {
        if (isOn) {
          if (!state.visibleKeys.includes(k)) state.visibleKeys.push(k);
        } else {
          state.visibleKeys = state.visibleKeys.filter((x) => x !== k);
        }
        schedulePrefsSave();
        requestViewRefresh();
      };
      const tipId = columnLabelId(k);
      if (ui && ui.checkbox) {
        const cb = ui.checkbox(label, checked, false);
        attachLabelTip(cb, tipId);
        if (ui.onCheck) ui.onCheck(cb, onToggle);
        else cb.addEventListener("change", () => onToggle(!!cb.checked));
        panel.appendChild(cb);
        return;
      }
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = checked;
      cb.addEventListener("change", () => onToggle(!!cb.checked));
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + label));
      attachLabelTip(lab, tipId);
      panel.appendChild(lab);
    });
  }

  function renderLegend() {
    const host = $("chart-legend");
    host.innerHTML = "";
    const ui = chrome();
    seriesDisplayMeta().forEach((s) => {
      let swatchStyle = "";
      let swatchClass = "";
      if (s.kind === "bar") {
        swatchStyle = "background:" + s.color + ";height:10px";
      } else {
        const a = s.alpha;
        swatchClass = "rs-swatch";
        swatchStyle =
          "background:linear-gradient(90deg,rgba(" + RS_NEG + "," + a + ") 50%,rgba(" + RS_POS + "," + a + ") 50%);" +
          "height:" + Math.max(2, Math.min(10, s.width / 2)) + "px";
      }
      const wrap = document.createElement("span");
      wrap.className = "legend-tip";
      const tipId = SERIES_LABEL_IDS[s.id] || "";
      if (tipId) wrap.dataset.labelTip = tipId;
      if (ui && ui.tag) {
        wrap.appendChild(ui.tag(s.label, { swatchStyle, swatchClass }));
      } else {
        const el = document.createElement("span");
        el.innerHTML =
          '<i class="' +
          swatchClass +
          '" style="' +
          swatchStyle +
          '"></i>' +
          s.label;
        wrap.appendChild(el);
      }
      host.appendChild(wrap);
    });
  }

  function stickyColClass(k) {
    if (k === "code") return "sticky-col sticky-col-code";
    if (k === "name") return "sticky-col sticky-col-name";
    return "";
  }

  function syncStickyColOffsets() {
    const table = $("grid");
    if (!table) return;
    const codeCell =
      table.querySelector("thead th.sticky-col-code") ||
      table.querySelector("tbody td.sticky-col-code");
    const width = codeCell ? Math.round(codeCell.getBoundingClientRect().width) : 0;
    if (width > 0) table.style.setProperty("--sticky-code-w", width + "px");
  }

  function scheduleStickyColOffsets() {
    syncStickyColOffsets();
    requestAnimationFrame(() => {
      syncStickyColOffsets();
      requestAnimationFrame(syncStickyColOffsets);
    });
  }

  function tdMarkup(row, k) {
    const def = state.colDefs[k] || { kind: "text" };
    const classes = [];
    let extra = "";
    if (def.kind === "signed1" || def.kind === "int") classes.push("num");
    if (def.kind === "news_bundle") classes.push("news-bundle");
    if (def.kind === "favorite") classes.push("fav-cell");
    let inner = cellHtml(row, k);
    if (def.kind === "signed1" && inner) {
      const raw = row[mapKey(k)];
      const ui = chrome();
      const range = ui && ui.cfRangeForLabel ? ui.cfRangeForLabel(k) : 1;
      const fmt = ui && ui.numberCellFormat ? ui.numberCellFormat(raw, range) : null;
      if (fmt) {
        classes.push("surface-cf-number");
        extra = ' style="--cell-hue:' + fmt.hue + ";--cell-alpha:" + fmt.alpha + '"';
      }
      if (raw != null && raw !== "" && Number.isFinite(Number(raw))) {
        extra += ' data-cf-value="' + escapeHtml(String(Number(raw))) + '"';
      }
    }
    if (k === "price_text") {
      classes.push("surface-cf-price");
      const priceApi = window.StockRadarPriceText;
      if (priceApi && priceApi.cellHtml) {
        inner = priceApi.cellHtml(row);
      } else if (inner) {
        const ui = chrome();
        const tone = ui && ui.priceTone ? ui.priceTone(displayPriceText(row)) : "neutral";
        inner = '<span class="surface-price-tag" data-tone="' + escapeHtml(tone) + '">' + inner + "</span>";
      }
    }
    const sticky = stickyColClass(k);
    if (sticky) classes.push.apply(classes, sticky.split(" "));
    const cls = classes.length ? ' class="' + classes.join(" ") + '"' : "";
    return "<td" + cls + extra + ">" + inner + "</td>";
  }

  function bindGridEvents() {
    const table = $("grid");
    if (!table || table.dataset.bound === "1") return;
    table.dataset.bound = "1";
    window.addEventListener("resize", scheduleStickyColOffsets);
    const tbody = table.tBodies[0];
    if (!tbody) return;
    tbody.addEventListener("click", (ev) => {
      const star = ev.target.closest("button.fav-star, td.fav-cell");
      if (star) {
        ev.preventDefault();
        ev.stopPropagation();
        if (state.freePreview) return;
        const btn = star.closest ? (star.matches("button.fav-star") ? star : star.querySelector("button.fav-star")) : star;
        const code = btn && btn.dataset ? btn.dataset.favCode : null;
        if (code) openFavFlyout(btn, code);
        return;
      }
      if (ev.target.closest("a")) return;
      const tr = ev.target.closest("tr[data-code]");
      if (tr) selectCode(tr.dataset.code, { scrollChart: true, toggle: true });
    });
    tbody.addEventListener("mouseover", (ev) => {
      const tr = ev.target.closest("tr[data-code]");
      if (!tr || !tbody.contains(tr)) return;
      const related = ev.relatedTarget;
      if (related && tr.contains(related)) return;
      setHoveredCode(tr.dataset.code, { from: "table" });
    });
    tbody.addEventListener("mouseout", (ev) => {
      const tr = ev.target.closest("tr[data-code]");
      if (!tr || !tbody.contains(tr)) return;
      const related = ev.relatedTarget;
      if (related && (related === tr || tr.contains(related))) return;
      if (state.hovered === tr.dataset.code) setHoveredCode(null);
    });
  }

  // Trailing halfwidth katakana is the monthly shortener's suffix
  // (ホールディングス / グループ / インターナショナル / コーポレーション).
  // Names still wider than that wrapped line break once at an existing
  // delimiter (・, space, hyphen), choosing the split with the shorter long line.
  const NAME_BREAK_MIN_PX = 142;
  const NAME_BREAK_SEPS = /[\u30FB\s\u3000\uFF0D-]/;
  let nameWidthCtx = null;

  function nameTextWidth(text) {
    if (!nameWidthCtx) {
      const probe = document.createElement("span");
      const grid = document.getElementById("grid");
      probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap";
      (grid || document.body).appendChild(probe);
      const cs = getComputedStyle(probe);
      probe.remove();
      nameWidthCtx = document.createElement("canvas").getContext("2d");
      nameWidthCtx.font = cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily;
      if ("letterSpacing" in nameWidthCtx) nameWidthCtx.letterSpacing = cs.letterSpacing;
    }
    return nameWidthCtx.measureText(text).width;
  }

  function nameDelimiterBreak(text) {
    if (nameTextWidth(text) <= NAME_BREAK_MIN_PX) return null;
    let best = null;
    for (let i = 0; i < text.length; i++) {
      if (!NAME_BREAK_SEPS.test(text.charAt(i))) continue;
      const left = text.slice(0, i).replace(/[\s\u3000]+$/, "");
      const right = text.slice(i + 1).replace(/^[\s\u3000]+/, "");
      if (!left || !right) continue;
      const width = Math.max(nameTextWidth(left), nameTextWidth(right));
      if (!best || width < best.width) best = { width: width, left: left, right: right };
    }
    if (!best || best.width >= nameTextWidth(text)) return null;
    return best;
  }

  function nameCellHtml(name) {
    const text = String(name);
    const match = /^(.*?)([\uFF61-\uFF9F]+)$/.exec(text);
    if (match) {
      const prefix = match[1].replace(/[\s\u3000]+$/, "");
      if (prefix) {
        return escapeHtml(prefix) + '<span class="name-hankaku">' + escapeHtml(match[2]) + "</span>";
      }
    }
    const split = nameDelimiterBreak(text);
    if (!split) return escapeHtml(text);
    return escapeHtml(split.left) + '<span class="name-break">' + escapeHtml(split.right) + "</span>";
  }

  function cellHtml(row, baseKey) {
    const key = mapKey(baseKey);
    const def = state.colDefs[baseKey] || { kind: "text" };
    if (def.kind === "favorite") {
      const code = String(row.code).padStart(4, "0");
      const on = isFavorite(code);
      const disabled = state.freePreview ? " disabled" : "";
      const cls = "fav-star" + (on ? " on" : "") + (state.freePreview ? " disabled" : "");
      return (
        '<button type="button" class="' +
        cls +
        '" data-fav-code="' +
        code +
        '" aria-pressed="' +
        (on ? "true" : "false") +
        '" aria-label="favorite lists"' +
        disabled +
        ">" +
        favCellInnerHtml(code) +
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
    if (baseKey === "price_text") return escapeHtml(displayPriceText(row));
    const v = row[key];
    if (baseKey === "name") return v == null ? "" : nameCellHtml(v);
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

  function headerCaption(label) {
    const text = String(label || "");
    if (text.indexOf("連動分を除く") === 0) return "連動分を除く\n" + text.slice("連動分を除く".length).trim();
    if (text.indexOf("パーフェクトオーダー") === 0 && text.length > "パーフェクトオーダー".length) {
      return "パーフェクトオーダー\n" + text.slice("パーフェクトオーダー".length);
    }
    if (text.indexOf("指数比の") === 0) return "指数比の\n" + text.slice("指数比の".length);
    if (text.indexOf("指数比 ") === 0) return "指数比\n" + text.slice("指数比 ".length);
    return text;
  }

  function renderTable(opts) {
    opts = opts || {};
    bindGridEvents();
    const rows = displayRows();
    $("row-count").textContent = "表示 " + rows.length + " / 全 " + state.rows.length + " 銘柄";
    const wrap = $("table-wrap");
    const prevTop = wrap ? wrap.scrollTop : 0;
    const prevLeft = wrap ? wrap.scrollLeft : 0;
    const thead = document.querySelector("#grid thead");
    const tbody = document.querySelector("#grid tbody");
    thead.innerHTML = "";
    const trh = document.createElement("tr");
    state.visibleKeys.forEach((k) => {
      const th = document.createElement("th");
      th.dataset.col = k;
      const tipId = columnLabelId(k);
      if (tipId) th.dataset.labelTip = tipId;
      const sticky = stickyColClass(k);
      if (sticky) th.className = sticky;
      const def = state.colDefs[k];
      const label = def ? def.label : mapKey(k);
      const caption = headerCaption(label);
      if (isNumericCol(k) || k === "favorite" || isTextFilterCol(k)) {
        th.classList.add("th-filterable");
        if (isNumericCol(k) || k === "favorite") th.classList.add("th-numeric");
        if (k !== "favorite" && state.sortKey === k) th.classList.add("th-sorted");
        if (k === "favorite" ? state.favOnly : colFilterActive(k)) th.classList.add("th-filtered");
        const ui = chrome();
        const btn = ui && ui.headerButton
          ? ui.headerButton({
              caption: caption,
              title: k === "favorite" ? "お気に入りフィルタ" : (isTextFilterCol(k) ? "文字列フィルタ" : "ソート / フィルタ"),
              sorted: k !== "favorite" && state.sortKey === k,
              filtered: k === "favorite" ? state.favOnly : colFilterActive(k),
            })
          : document.createElement("button");
        if (!ui || !ui.headerButton) {
          btn.type = "button";
          btn.textContent = caption;
          btn.title = k === "favorite" ? "お気に入りフィルタ" : (isTextFilterCol(k) ? "文字列フィルタ" : "ソート / フィルタ");
        }
        btn.classList.add("th-filter-btn");
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          if (k === "favorite") openFavFilterMenu(th);
          else if (isTextFilterCol(k)) openTextFilterMenu(th, k);
          else openFilterMenu(th, k);
        });
        th.appendChild(btn);
      } else {
        th.textContent = caption;
      }
      trh.appendChild(th);
    });
    thead.appendChild(trh);

    const keys = state.visibleKeys;
    const parts = new Array(rows.length);
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const code = String(row.code).padStart(4, "0");
      const codeEsc = escapeHtml(code);
      let cls = "";
      if (state.selected === code) cls = " selected";
      else if (state.hovered === code) cls = " is-hover";
      let tds = "";
      for (let j = 0; j < keys.length; j++) tds += tdMarkup(row, keys[j]);
      parts[i] = "<tr data-code=\"" + codeEsc + "\"" + (cls ? " class=\"" + cls.trim() + "\"" : "") + ">" + tds + "</tr>";
    }
    tbody.innerHTML = parts.join("");
    updateSearchMiss(rows.length);
    if (wrap) {
      wrap.scrollTop = prevTop;
      wrap.scrollLeft = prevLeft;
    }
    scheduleStickyColOffsets();

    const codes = rows.map((r) => String(r.code).padStart(4, "0"));
    if (opts.charts === "skip") return;
    if (opts.charts !== "force" && sameCodeList(state.visibleChartCodes, codes)) return;
    state.visibleChartCodes = codes;
    refreshCharts(codes);
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
    const hoverIndex =
      canvas._hoverIndex == null ? n - 1 : Math.max(0, Math.min(n - 1, canvas._hoverIndex));
    const colW = n <= 1 ? zBarW : Math.max(zBarW, xSpan / (n - 1));
    drawChartHoverMarker(ctx, xAt, padT, plotH, hoverIndex, colW, dpr);
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

  function drawChartHoverMarker(ctx, xAt, padT, plotH, index, colW, dpr) {
    const x = xAt(index);
    const hw = Math.max(colW, 1 * dpr);
    ctx.save();
    ctx.fillStyle = "rgba(110,168,254,0.16)";
    ctx.fillRect(x - hw / 2, padT, hw, plotH);
    ctx.strokeStyle = "rgba(110,168,254,0.85)";
    ctx.lineWidth = Math.max(1, dpr);
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + plotH);
    ctx.stroke();
    ctx.restore();
  }

  function latestChartIndex(dates) {
    return Math.max(0, (dates || []).length - 1);
  }

  function chartHoverCellHtml(seriesId, text, raw, fit) {
    const n = raw == null ? NaN : Number(raw);
    const ui = chrome();
    const range = ui && ui.cfRangeForLabel ? ui.cfRangeForLabel(seriesId) : 1;
    const fmt =
      Number.isFinite(n) && ui && ui.numberCellFormat
        ? ui.numberCellFormat(n, range)
        : null;
    let extra = "";
    const classes = ["chart-hover-cell"];
    if (fit) classes.push("chart-hover-fit");
    if (fmt) {
      classes.push("surface-cf-number");
      extra = ' style="--cell-hue:' + fmt.hue + ";--cell-alpha:" + fmt.alpha + '"';
    }
    return (
      '<span class="' + classes.join(" ") + '"' + extra + ">" + escapeHtml(text) + "</span>"
    );
  }

  function fillChartHoverTable(hoverEl, dates, seriesMap, index) {
    if (!hoverEl) return;
    const n = (dates || []).length;
    if (!n) {
      hoverEl.innerHTML = "";
      return;
    }
    const idx = Math.max(0, Math.min(n - 1, index));
    const series = seriesDisplayMeta();
    const colCount = 1 + series.length;
    const head = ['<span class="chart-hover-date chart-hover-head"></span>'];
    series.forEach((s) => {
      const tipId = SERIES_LABEL_IDS[s.id] || "";
      const fit = s.id === "z_disp" ? " chart-hover-fit" : "";
      head.push(
        '<span class="chart-hover-cell chart-hover-head' + fit + '"' +
          (tipId ? ' data-label-tip="' + tipId + '"' : "") +
          ">" +
          '<span class="surface-label-compact"><span class="surface-label-compact-text">' + escapeHtml(s.label) + "</span></span>" +
          "</span>"
      );
    });
    const values = [
      '<span class="chart-hover-date">' + escapeHtml(dates[idx] || "") + "</span>",
    ];
    series.forEach((s) => {
      const raw = (seriesMap[s.id] || [])[idx];
      const text = raw == null || Number.isNaN(Number(raw)) ? "null" : fmtSigned1(raw);
      values.push(chartHoverCellHtml(s.id, text, raw, s.id === "z_disp"));
    });
    hoverEl.innerHTML =
      '<div class="chart-hover-table" style="--chart-hover-cols:' +
      colCount +
      '">' +
      head.join("") +
      values.join("") +
      "</div>";
  }

  function setChartHoverIndex(canvas, dates, seriesMap, hoverEl, index) {
    if (!canvas) return;
    const idx = Math.max(0, Math.min(latestChartIndex(dates), index));
    const prev = canvas._hoverIndex;
    canvas._hoverIndex = idx;
    fillChartHoverTable(hoverEl, dates, seriesMap, idx);
    if (prev !== idx) {
      drawChart(canvas, dates, seriesMap, hoverEl, canvas._chartYShift || 0);
    }
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
    setChartHoverIndex(canvas, dates, seriesMap, hoverEl, best);
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
      if (!canvas.matches(":hover")) {
        setChartHoverIndex(canvas, dates, seriesMap, hoverEl, latestChartIndex(dates));
      }
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
    canvas.addEventListener("pointerleave", () => {
      if (canvas._chartPan) return;
      setChartHoverIndex(canvas, dates, seriesMap, hoverEl, latestChartIndex(dates));
    });
  }


  function asOfQuery() {
    return "as_of=" + encodeURIComponent(state.asOf || "");
  }

  async function fetchSeries(codes) {
    const missing = codes.filter((c) => !state.seriesCache[c]);
    if (!missing.length) return;
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

  function applyChartCardChrome(shell, selected, hovered) {
    if (!shell) return;
    shell.classList.toggle("is-selected", !!selected);
    shell.classList.toggle("is-hover", !!hovered);
    const appearance = selected ? "accent" : hovered ? "filled-outlined" : "outlined";
    if (shell.appearance !== appearance) shell.appearance = appearance;
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
      const selected = !!sel && c === sel;
      const hovered = !!hov && c === hov && c !== sel;
      card.classList.toggle("selected", selected);
      card.classList.toggle("is-hover", hovered);
      applyChartCardChrome(card.querySelector("wa-card"), selected, hovered);
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
    if (opts.from === "table") {
      if (!state.selected) scrollChartCardIntoView(next);
    } else if (opts.from === "chart") {
      scrollTableRowIntoView(next);
    }
  }

  function selectCode(code, opts) {
    opts = opts || {};
    const next = code ? String(code).padStart(4, "0") : null;
    if (opts.toggle && next && state.selected === next) {
      state.selected = null;
      syncHighlightClasses();
      showWebEmpty();
      return;
    }
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
    if (sameCodeList(state.visibleChartCodes, codes)) return;
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
      const slot = card.querySelector(".chart-slot, [data-chart-canvas]");
      if (slot) slot.replaceChildren(canvas);
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
    const hoverEl = card.querySelector(".hover, [data-chart-hover]");
    canvas._hoverIndex = latestChartIndex(dates);
    fillChartHoverTable(hoverEl, dates, seriesMap, canvas._hoverIndex);
    drawChart(canvas, dates, seriesMap, hoverEl, 0);
    bindChartPan(canvas, dates, seriesMap, hoverEl);
    card.dataset.drawn = "1";
  }

  function makeFavStarButton(code) {
    const c = padFavCode(code);
    const on = isFavorite(c);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "fav-star" + (on ? " on" : "") + (state.freePreview ? " disabled" : "");
    btn.dataset.favCode = c;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.setAttribute("aria-label", "favorite lists");
    if (state.freePreview) btn.disabled = true;
    btn.innerHTML = favCellInnerHtml(c);
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (state.freePreview) return;
      openFavFlyout(btn, c);
    });
    return btn;
  }

  function makeChartCard(code) {
    const row = findRowByCode(code) || {};
    const ui = chrome();
    const card = document.createElement("div");
    card.className = "chart-card";
    card.dataset.code = code;
    const selected = state.selected === code;
    const hovered = state.hovered === code && !selected;
    if (selected) card.classList.add("selected");
    if (hovered) card.classList.add("is-hover");
    const shell = ui && ui.chartCard ? ui.chartCard() : null;
    if (shell) {
      const heading = shell.querySelector("[data-chart-title]");
      if (heading) heading.textContent = code + " " + (row.name || "");
      const favHost = shell.querySelector("[data-chart-fav]");
      if (favHost) favHost.replaceChildren(makeFavStarButton(code));
      applyChartCardChrome(shell, selected, hovered);
      card.appendChild(shell);
    } else {
      card.innerHTML =
        "<div class=\"chart-card-head\"><h4>" + escapeHtml(code) + " " + escapeHtml(row.name || "") + "</h4></div>" +
        "<div class=\"hover\"></div>" +
        "<div class=\"chart-slot\" aria-hidden=\"true\"></div>";
      const head = card.querySelector(".chart-card-head");
      if (head) head.appendChild(makeFavStarButton(code));
    }
    card.addEventListener("mouseenter", () => setHoveredCode(code, { from: "chart" }));
    card.addEventListener("mouseleave", () => {
      if (state.hovered === code) setHoveredCode(null);
    });
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button.fav-star, .fav-flyout")) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      const canvas = card.querySelector("canvas");
      if (canvas && canvas._suppressClick) {
        canvas._suppressClick = false;
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      selectCode(code, { scrollTable: true, toggle: true });
    });
    return card;
  }

  function ensureChartObserver(host) {
    if (state.chartObserver) return state.chartObserver;
    state.chartObserver = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) paintChartCard(en.target);
      });
    }, { root: host, rootMargin: "160px 0px", threshold: 0.01 });
    return state.chartObserver;
  }

  function refreshCharts(codes) {
    const host = $("chart-host");
    if (!host) return;
    const seen = new Set();
    const ordered = [];
    (codes || []).forEach((c) => {
      const code = String(c).padStart(4, "0");
      if (seen.has(code)) return;
      seen.add(code);
      ordered.push(code);
    });

    const prevScroll = host.scrollTop;
    const existing = new Map();
    host.querySelectorAll(".chart-card[data-code]").forEach((card) => {
      existing.set(card.dataset.code, card);
    });
    const observer = ensureChartObserver(host);
    const keep = new Set(ordered);
    existing.forEach((card, code) => {
      if (keep.has(code)) return;
      observer.unobserve(card);
      card.remove();
    });
    const frag = document.createDocumentFragment();
    ordered.forEach((code) => {
      let card = existing.get(code);
      if (!card) {
        card = makeChartCard(code);
        observer.observe(card);
      } else {
        const selected = state.selected === code;
        const hovered = state.hovered === code && !selected;
        card.classList.toggle("selected", selected);
        card.classList.toggle("is-hover", hovered);
        applyChartCardChrome(card.querySelector("wa-card"), selected, hovered);
      }
      frag.appendChild(card);
    });
    host.appendChild(frag);

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
  const TAB_TIP_IDS = {
    overview: "web_overview",
    chart: "web_chart",
    news: "web_news",
    news_candidates: "web_news_candidates",
    link_buffett: "web_buffett",
    link_minkabu: "web_minkabu",
    link_yahoo: "web_yahoo",
  };
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
    schedulePrefsSave();
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
    const ui = chrome();
    TAB_SETTINGS_META.forEach((meta) => {
      const onToggle = (isOn) => {
        state.tabSettings[meta.key] = !!isOn;
        saveTabSettings();
        const row = state.rows.find((r) => String(r.code).padStart(4, "0") === state.selected) || null;
        renderKabutanTabBar(row);
        if (row) applyKabutanUrl(row, state.kabutanMode);
        else showWebEmpty();
      };
      const tipId = TAB_TIP_IDS[meta.key] || "";
      if (ui && ui.checkbox) {
        const cb = ui.checkbox(meta.label, !!state.tabSettings[meta.key], false);
        attachLabelTip(cb, tipId);
        if (ui.onCheck) ui.onCheck(cb, onToggle);
        else cb.addEventListener("change", () => onToggle(!!cb.checked));
        panel.appendChild(cb);
        return;
      }
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.tabSettings[meta.key];
      cb.addEventListener("change", () => onToggle(!!cb.checked));
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + meta.label));
      attachLabelTip(lab, tipId);
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
    const ui = chrome();
    const children = [];
    let panelIndex = 0;
    let unknownNote = "";

    function addTab(id, label, opts) {
      const options = opts || {};
      const panel = "kabutan-panel-" + panelIndex;
      panelIndex += 1;
      const active = state.kabutanMode === id;
      if (ui && ui.tab) {
        const t = ui.tab({
          panel,
          label,
          title: options.title,
          disabled: options.disabled,
          active,
          candidate: options.candidate,
        });
        t.dataset.kab = id;
        if (options.labelTip) t.dataset.labelTip = options.labelTip;
        if (options.cand) t.dataset.cand = options.cand;
        children.push(t);
        if (ui.tabPanel) children.push(ui.tabPanel(panel, active));
        return;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kab = id;
      btn.textContent = label;
      if (options.disabled) btn.disabled = true;
      if (options.title) btn.title = options.title;
      if (options.labelTip) btn.dataset.labelTip = options.labelTip;
      if (options.cand) btn.dataset.cand = options.cand;
      if (options.candidate) btn.classList.add("is-candidate");
      children.push(btn);
    }

    ["overview", "chart", "news"].forEach((id) => {
      if (!state.tabSettings[id]) return;
      const meta = TAB_SETTINGS_META.find((x) => x.key === id);
      addTab(id, meta ? meta.label : id, { labelTip: TAB_TIP_IDS[id] });
    });

    ["link_buffett", "link_minkabu", "link_yahoo"].forEach((id) => {
      if (!state.tabSettings[id]) return;
      const meta = TAB_SETTINGS_META.find((x) => x.key === id);
      addTab(id, meta ? meta.label : id, {
        disabled: !!(row && !row[id]),
        title: row && !row[id] ? "URL\u306a\u3057" : "",
        labelTip: TAB_TIP_IDS[id],
      });
    });

    if (state.tabSettings.news_candidates && row) {
      if (isUnknownMaterialRow(row)) {
        unknownNote = UNKNOWN_MATERIAL_TEXT;
      } else {
        const items = eventNewsItems(row).filter((it) => it.title !== UNKNOWN_MATERIAL_TEXT);
        items.forEach((it) => {
          addTab("cand:" + it.n, tabLabel10(it.title), {
            title: it.title + (it.url ? ("\n" + it.url) : ""),
            cand: String(it.n),
            candidate: true,
            labelTip: "event_news_bundle",
          });
        });
      }
    }

    main.dataset.syncing = "true";
    main.replaceChildren(...children);
    const noteClass = "surface-tab-note";
    const tabsBar = main.parentElement;
    if (tabsBar) {
      tabsBar.querySelectorAll("." + noteClass + ", .kabutan-unknown-material").forEach((el) => el.remove());
      if (unknownNote) {
        const span = document.createElement("span");
        span.className = noteClass + " kabutan-unknown-material";
        span.textContent = unknownNote;
        main.insertAdjacentElement("afterend", span);
      }
    }
    ensureValidKabutanMode(row);
    setKabutanActive(state.kabutanMode);
    Promise.resolve(main.updateComplete).then(() => {
      requestAnimationFrame(() => {
        delete main.dataset.syncing;
      });
    });
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
      const n = Number(String(mode).slice(5));
      const item = eventNewsItems(row).find((it) => it.n === n);
      const url = item && item.url;
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
    let activePanel = "";
    host.querySelectorAll("[data-kab]").forEach((b) => {
      const on = b.dataset.kab === mode;
      b.classList.toggle("active", on);
      if (b.tagName === "WA-TAB") {
        if (on) {
          b.setAttribute("active", "");
          activePanel = b.getAttribute("panel") || "";
        } else {
          b.removeAttribute("active");
        }
      }
    });
    if (activePanel) host.setAttribute("active", activePanel);
  }

  // 株探のページ先頭はバナー広告とパンくず。本文の #container はその直下。
  // 別オリジンのため iframe の scrollTop は触れない。フラグメントで初期位置だけ合わせる。
  function kabutanEmbedUrl(url) {
    try {
      const parsed = new URL(url);
      const host = parsed.hostname.toLowerCase();
      if (host !== "kabutan.jp" && host !== "www.kabutan.jp") return url;
      if (parsed.hash) return url;
      parsed.hash = "container";
      return parsed.toString();
    } catch (err) {
      return url;
    }
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
      frame.src = kabutanEmbedUrl(url);
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
    const ui = chrome();
    const items = (state.availableDates || []).map((d) => ({ value: d, text: d }));
    if (ui && ui.fillSelect) ui.fillSelect(sel, items, state.asOf);
    else {
      sel.replaceChildren();
      state.availableDates.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d;
        opt.textContent = d;
        sel.appendChild(opt);
      });
    }
    if (!state.asOf) return;
    sel.value = state.asOf;
    [...sel.querySelectorAll("wa-option, option")].forEach((opt) => {
      if (opt.value === state.asOf) opt.setAttribute("selected", "");
      else opt.removeAttribute("selected");
    });
  }

  function formatJstStamp(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const parts = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const get = (type) => {
      const part = parts.find((item) => item.type === type);
      return part ? part.value : "";
    };
    const stamp = get("year") + "-" + get("month") + "-" + get("day") + " " + get("hour") + ":" + get("minute");
    return stamp.trim() === "-" ? "" : stamp + " JST";
  }

  function updateDataStamp() {
    const el = $("data-updated");
    if (!el) return;
    const stamp = formatJstStamp(state.dataUpdatedAt);
    el.textContent = stamp ? ("最終更新 " + stamp) : "";
  }

  function updateBanner() {
    const source = state.meta.csv_source === "ohlc_universe"
      ? " / ニュースと銘柄名は空です（現行のOHLCユニバース）"
      : "";
    $("asof-banner").textContent =
      "基準日 " + state.meta.as_of +
      " / " + state.meta.n_rows + "銘柄" +
      " / " + ((state.meta.axis_dates || []).length) + "営業日" +
      source +
      " | 内部向け初回ライブ。投資助言ではありません。";
    updateDataStamp();
    if (
      state.bundleNotice &&
      state.bundleNotice.trade_date === state.asOf &&
      state.bundleNotice.committed_at_utc === state.dataUpdatedAt
    ) {
      const notice = $("bundle-notice");
      if (notice) notice.hidden = true;
      state.bundleNotice = null;
    }
  }

  function priceTextAvailable() {
    return state.allKeys.includes("price_text") || state.allKeys.includes("candle_labels");
  }

  function computeDefaultVisibleKeys() {
    return XLSX_DEFAULT.map((c) => c.key).filter((k) => {
      if (k === "date" || HIDDEN_COL_KEYS.has(k)) return false;
      if (LINK_KEYS_OPTIONAL.has(k)) return false;
      if (k === "favorite") return true;
      if (k === "price_text") return priceTextAvailable();
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
  }

  function keyAvailable(k) {
    if (k === "favorite") return true;
    if (k === "price_text") return priceTextAvailable();
    return state.allKeys.includes(k) || state.allKeys.includes(mapKey(k));
  }

  function orderVisibleKeys(keys, defaults) {
    const preferred = window.__WEB_UI_VISIBLE_ORDER;
    const basis = Array.isArray(preferred) && preferred.length ? preferred : (defaults || []);
    const have = new Set(keys);
    const ordered = [];
    basis.forEach((k) => {
      if (have.has(k)) {
        ordered.push(k);
        have.delete(k);
      }
    });
    keys.forEach((k) => {
      if (have.has(k)) {
        ordered.push(k);
        have.delete(k);
      }
    });
    return ordered;
  }

  function reconcileVisibleKeys(defaults) {
    const prevAll = new Set(state.prevAllKeys || []);
    const newlyInBundle = new Set(state.allKeys.filter((k) => !prevAll.has(k)));
    if (!state.visibleKeysReady) {
      const saved = Array.isArray(state.prefsVisibleKeys) ? state.prefsVisibleKeys : [];
      const snapshot = Array.isArray(state.prefsDefaultKeysSnapshot)
        ? state.prefsDefaultKeysSnapshot
        : [];
      if (!saved.length) {
        state.visibleKeys = defaults.slice();
      } else {
        const kept = saved.filter(keyAvailable);
        const newly = defaults.filter(
          (k) => !snapshot.includes(k) && !kept.includes(k) && keyAvailable(k)
        );
        state.visibleKeys = orderVisibleKeys([...kept, ...newly], defaults);
      }
      state.visibleKeysReady = true;
    } else {
      const kept = state.visibleKeys.filter(keyAvailable);
      const add = defaults.filter(
        (k) => newlyInBundle.has(k) && !kept.includes(k) && keyAvailable(k)
      );
      state.visibleKeys = orderVisibleKeys([...kept, ...add], defaults);
    }
    state.prevAllKeys = state.allKeys.slice();
    state.prefsDefaultKeysSnapshot = defaults.slice();
  }

  async function loadSnapshot(asOf) {
    bootProgress("データを読み込んでいます", 0.58);
    state.asOf = asOf;
    state.seriesCache = {};
    state.visibleChartCodes = [];
    state.selected = null;
    state.hovered = null;
    if (state.chartObserver) {
      state.chartObserver.disconnect();
      state.chartObserver = null;
    }
    $("chart-host").innerHTML = "";
    showWebEmpty();
    state.kabutanMode = "overview";
    renderKabutanTabBar(null);

    const aliased = await loadBundle(asOf, state.bench);
    state.meta = {
      as_of: aliased.as_of,
      n_rows: aliased.n_rows,
      n_excluded: 0,
      axis_dates: aliased.axis_dates || [],
      csv_source: aliased.csv_source || "",
    };
    state.rows = aliased.rows || [];
    state.seriesCache = aliased.series || {};
    const keySet = new Set();
    state.rows.forEach((r) => Object.keys(r).forEach((k) => keySet.add(k)));
    state.allKeys = [...keySet].sort();
    ensureColDefs();
    reconcileVisibleKeys(computeDefaultVisibleKeys());

    bootProgress("画面を描画しています", 0.96);
    updateBanner();
    fillAsOfSelect();
    renderColsPanel();
    renderTable();
    const app = $("app-root");
    if (app) app.hidden = false;
    hideBootProgress();
  }

  const BUNDLE_WATCH_MS = 300000;
  let bundleWatchTimer = null;

  function latestBundleCommit(commits, bench) {
    let best = null;
    for (const row of commits || []) {
      if (!row || row.benchmark !== bench || !row.trade_date) continue;
      const at = String(row.committed_at_utc || "");
      if (
        !best ||
        row.trade_date > best.trade_date ||
        (row.trade_date === best.trade_date && at > String(best.committed_at_utc || ""))
      ) {
        best = row;
      }
    }
    return best;
  }

  function bundleCommitKey(row) {
    if (!row) return "";
    return String(row.trade_date || "") + "|" + String(row.committed_at_utc || "");
  }

  function hideBundleNotice() {
    const notice = $("bundle-notice");
    if (notice) notice.hidden = true;
    state.bundleNotice = null;
  }

  function showBundleNotice(commit, datesBefore) {
    const el = $("bundle-notice");
    const text = $("bundle-notice-text");
    if (!el || !text || !commit) return;
    const date = String(commit.trade_date);
    const known = (datesBefore || []).indexOf(date) >= 0;
    state.bundleNotice = {
      trade_date: date,
      committed_at_utc: commit.committed_at_utc || null,
    };
    text.textContent = known && date === state.asOf
      ? "基準日 " + date + " の束が更新されました。最終更新を反映しました。表示中の数値は、読み込み直すまでそのままです。"
      : "基準日 " + date + " の束が配信されました。基準日の選択肢に追加しました。表示中の数値は、その基準日を選ぶまでそのままです。";
    el.hidden = false;
  }

  function applyBundleIndex(payload, announce) {
    const commits = Array.isArray(payload && payload.commits) ? payload.commits : null;
    const incoming = Array.isArray(payload && payload.dates) ? payload.dates.filter(Boolean) : [];
    const datesBefore = (state.availableDates || []).slice();
    if (incoming.length) {
      const merged = incoming.slice();
      if (state.asOf && merged.indexOf(state.asOf) < 0) merged.push(state.asOf);
      merged.sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
      const changed = merged.join("\n") !== datesBefore.join("\n");
      state.availableDates = merged;
      if (changed) fillAsOfSelect();
    }
    if (!commits) return;
    const current = commits.find((row) => row.trade_date === state.asOf && row.benchmark === state.bench);
    if (current && current.committed_at_utc && current.committed_at_utc !== state.dataUpdatedAt) {
      state.dataUpdatedAt = current.committed_at_utc;
      updateDataStamp();
    }
    const latest = latestBundleCommit(commits, state.bench);
    const key = bundleCommitKey(latest);
    if (!announce) {
      state.seenBundleKey = key;
      return;
    }
    if (key && key !== state.seenBundleKey) {
      showBundleNotice(latest, datesBefore);
      state.seenBundleKey = key;
    }
  }

  function bundleWatchOpen(now) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Tokyo",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(now || new Date());
    const get = (type) => {
      const part = parts.find((item) => item.type === type);
      return part ? part.value : "";
    };
    const weekday = get("weekday");
    if (weekday === "Sat" || weekday === "Sun") return false;
    const minutes = Number(get("hour")) * 60 + Number(get("minute"));
    return minutes >= 16 * 60 && minutes < 22 * 60;
  }

  async function refreshBundleIndex() {
    if (document.visibilityState === "hidden") return;
    if (!bundleWatchOpen()) return;
    let payload;
    try {
      payload = await bffFetch("/v1/dates");
    } catch (err) {
      if (err && err.t5 === "login" && !liveCtx() && bundleWatchTimer) {
        clearInterval(bundleWatchTimer);
        bundleWatchTimer = null;
      }
      return;
    }
    applyBundleIndex(payload, true);
  }

  function startBundleWatch(initialPayload) {
    applyBundleIndex(initialPayload, false);
    const dismiss = $("bundle-notice-dismiss");
    if (dismiss && dismiss.dataset.bound !== "1") {
      dismiss.dataset.bound = "1";
      dismiss.addEventListener("click", hideBundleNotice);
    }
    if (bundleWatchTimer) return;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshBundleIndex();
    });
    bundleWatchTimer = setInterval(refreshBundleIndex, BUNDLE_WATCH_MS);
  }

  async function boot() {
    bindLabelTips();
    bootProgress("基準日の一覧を取得しています", 0.42);
    const datesPayload = await bffFetch("/v1/dates");
    state.bundleIndex = datesPayload;
    state.availableDates = datesPayload.dates || [];
    state.asOf = datesPayload.default || (state.availableDates[0] || null);
    if (!state.asOf) {
      showT5("temporary");
      fillAsOfSelect();
      return;
    }

    const uiBoot = chrome();
    const onAsof = (value) => {
      loadSnapshot(value).catch((err) => {
        hideBootProgress();
        $("asof-banner").textContent = "基準日の切り替えに失敗しました。 " + err;
      });
    };
    const onBench = (value) => {
      state.bench = value;
      schedulePrefsSave();
      loadSnapshot(state.asOf).catch((err) => {
        showT5(err && err.t5 ? err.t5 : "temporary");
      });
    };
    if (uiBoot && uiBoot.onSelectChange) {
      uiBoot.onSelectChange($("asof-mode"), onAsof);
      uiBoot.onSelectChange($("bench-mode"), onBench);
    } else {
      $("asof-mode").addEventListener("change", (e) => onAsof(e.target.value));
      $("bench-mode").addEventListener("change", (e) => onBench(e.target.value));
    }
    const ctx = liveCtx();
    state.userId = (ctx && ctx.uid) || "operator";
    state.freePreview = false;
    try {
      bootProgress("表示設定を読み込んでいます", 0.52);
      const prefs = await bffFetch("/v1/preferences");
      await applyPrefsBag(prefs.bag || {});
    } catch (err) {
      if (err && err.t5 === "login") {
        showT5("login");
        return;
      }
      if (err && err.t5 === "unavailable") {
        showT5("unavailable");
        return;
      }
      showT5("temporary");
      return;
    }
    setFavoritesUiEnabled(!state.freePreview);
    syncFilterModalUi();
    bindAccountMenu();
    bindConfirmDialog();
    markNonCredentialInput($("fav-list-new-name"), "list-label");
    markNonCredentialInput($("fav-list-rename"), "list-label");
    bindHalfWidthCodeInput($("fav-list-add-code"));
    const favAddCode = $("fav-list-add-code");
    if (favAddCode) {
      favAddCode.addEventListener("input", updateFavAddCodeHint);
      favAddCode.addEventListener("wa-input", updateFavAddCodeHint);
    }
    const favAdd = $("fav-list-add");
    if (favAdd) {
      favAdd.addEventListener("click", () => {
        const nameEl = $("fav-list-new-name");
        const created = createFavList(nameEl ? nameEl.value : "");
        if (created && nameEl) nameEl.value = "";
        if (created) {
          state.favModalListId = created.id;
          renderFavListsModal();
        }
      });
    }
    const favRename = $("fav-list-rename");
    if (favRename) {
      favRename.addEventListener("change", () => commitFavListRename());
      favRename.addEventListener("wa-change", () => commitFavListRename());
      favRename.addEventListener("wa-blur", () => commitFavListRename());
      favRename.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          commitFavListRename();
          favRename.blur();
        }
      });
    }
    const favDelete = $("fav-list-delete");
    if (favDelete) {
      favDelete.addEventListener("click", () => {
        const list = findFavList(state.favModalListId);
        if (!list || state.favLists.length <= 1) return;
        confirmDestructive("「" + list.name + "」を削除しますか？", () => deleteFavList(list.id));
      });
    }
    const favCodeForm = $("fav-lists-add-code-form");
    if (favCodeForm) {
      favCodeForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const input = $("fav-list-add-code");
        const btn = $("fav-list-add-code-btn");
        if ((input && input.disabled) || (btn && btn.disabled)) return;
        const ok = addCodeToFavList(state.favModalListId, input ? input.value : "");
        if (ok && input) input.value = "";
        updateFavAddCodeHint();
      });
    }
    const favClose = $("fav-lists-close");
    const favDone = $("fav-lists-done");
    const favModal = $("fav-lists-modal");
    if (favClose) favClose.addEventListener("click", () => closeFavListsModal());
    if (favDone) favDone.addEventListener("click", () => closeFavListsModal());
    if (favModal) {
      favModal.addEventListener("click", (ev) => {
        if (ev.target && ev.target.getAttribute("data-fav-lists-close") === "1") closeFavListsModal();
      });
    }
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
    const excludeCb = $("filter-exclude-all-rs-neg");
    const onExclude = (checked) => {
      if (state.freePreview) {
        excludeCb.checked = false;
        state.excludeAllRsNeg = false;
        syncFilterModalUi();
        return;
      }
      state.excludeAllRsNeg = !!checked;
      schedulePrefsSave();
      requestViewRefresh();
    };
    if (uiBoot && uiBoot.onCheck) uiBoot.onCheck(excludeCb, onExclude);
    else excludeCb.addEventListener("change", (e) => onExclude(e.target.checked));
    document.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape") return;
      if ($("confirm-dialog") && $("confirm-dialog").open) return;
      if ($("fav-lists-modal") && !$("fav-lists-modal").classList.contains("hidden")) closeFavListsModal();
      if (!$("cols-modal").classList.contains("hidden")) closeColsModal();
      if (!$("filter-modal").classList.contains("hidden")) closeFilterModal();
      if (!$("tab-settings-modal").classList.contains("hidden")) closeTabSettingsModal();
      closeFilterMenu();
      closeAccountMenu();
      closeFavFlyout();
    });
    document.addEventListener("click", (ev) => {
      const t = ev.target;
      if (t && t.closest && t.closest(".col-filter-menu, .fav-filter-anchor, .fav-flyout, .account-menu, .th-filter-btn, [data-surface-header], wa-dropdown")) {
        return;
      }
      closeFilterMenu();
      closeAccountMenu();
      closeFavFlyout();
    });
    const tabHost = $("kabutan-tabs-main");
    function applyKabutanFromTab(tab) {
      if (!tab || tab.disabled) return;
      const mode = tab.dataset.kab;
      if (!mode) return;
      state.kabutanMode = mode;
      setKabutanActive(state.kabutanMode);
      const row = state.rows.find((r) => String(r.code).padStart(4, "0") === state.selected);
      if (row) applyKabutanUrl(row, state.kabutanMode);
    }
    tabHost.addEventListener("wa-tab-show", (ev) => {
      if (tabHost.dataset.syncing === "true") return;
      const name = ev.detail && ev.detail.name;
      const tab = [...tabHost.querySelectorAll("wa-tab")].find((el) => el.getAttribute("panel") === name);
      applyKabutanFromTab(tab);
    });
    tabHost.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-kab]");
      if (!btn || !tabHost.contains(btn)) return;
      if (btn.tagName === "WA-TAB") return;
      if (btn.disabled) return;
      ev.preventDefault();
      applyKabutanFromTab(btn);
    });

    ensureColDefs();
    showWebEmpty();
    initKabutanSplitter();
    renderLegend();
    await loadSnapshot(state.asOf);
    startBundleWatch(datesPayload);
  }

  window.__webUiBoot = function webUiBoot() {
    return boot().catch((err) => {
      showT5(err && err.t5 ? err.t5 : "temporary");
    });
  };
})();
