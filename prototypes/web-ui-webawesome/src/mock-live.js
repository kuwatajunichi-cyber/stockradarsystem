import "./theme.js";

const PROTOTYPE_DATES = ["2026-09-30", "2026-09-29", "2026-09-28"];

const COMPANIES = [
  ["7011", "三菱重工業", "RANGE_LARGE,BODY_MARUBOZU_LIKE,DIR_BULL", 4.8, 2.7, 0.7, 0.84, 0.62, 0.41, 0.16, 0.58, ["防衛関連の大型案件報道", "受注残の更新", "海外事業の進捗観測"]],
  ["5803", "フジクラ", "GAP_UP,RANGE_VERY_LARGE,WICK_UPPER_LONG,BODY_LONG,DIR_BULL", 4.3, 2.2, 0.61, 0.76, 0.71, 0.53, 0.37, 0.66, ["データセンター需要観測", "光ファイバー増産報道", "業績予想の修正"]],
  ["6857", "アドバンテスト", "RANGE_LARGE,WICK_UPPER_LONG,BODY_MIDDLE,DIR_BULL", 3.9, 1.8, 0.44, 0.69, 0.54, 0.31, 0.49, 0.42, ["半導体テスト需要", "目標株価変更", "先端品の受注観測"]],
  ["9984", "ソフトバンクグループ", "GAP_UP,RANGE_LARGE,BODY_LONG,DIR_BULL", 3.5, 1.3, 0.35, 0.57, 0.38, 0.12, -0.08, 0.28, "AI投資先の評価額報道"],
  ["7203", "トヨタ自動車", "RANGE_SMALL,WICK_LOWER_LONG,BODY_SMALL,DIR_BULL", 3.1, 0.9, 0.22, 0.46, 0.19, 0.08, 0.21, 0.17, "北米販売実績"],
  ["6501", "日立製作所", "RANGE_LARGE,BODY_MARUBOZU_LIKE,DIR_BULL", 2.7, 1.1, 0.28, 0.52, 0.48, 0.4, 0.33, 0.45, "DX事業の成長観測"],
  ["8306", "三菱UFJ FG", "RANGE_SMALL,WICK_BOTH_PRESENT,DOJI", 2.4, 0.4, 0.08, 0.33, 0.42, 0.39, 0.51, 0.4, "国内金利見通し"],
  ["4063", "信越化学工業", "RANGE_SMALL,WICK_LOWER_PRESENT,BODY_SMALL,DIR_BEAR", 2.1, -0.1, -0.03, 0.14, 0.08, -0.12, -0.18, -0.04, null],
  ["8035", "東京エレクトロン", "RANGE_LARGE,WICK_UPPER_PRESENT,BODY_MIDDLE,DIR_BEAR", 1.9, -0.5, -0.12, -0.09, 0.17, 0.22, 0.29, 0.11, "半導体装置の輸出統計"],
  ["9432", "NTT", "RANGE_VERY_SMALL,DOJI", 1.5, -0.2, -0.05, 0.08, -0.04, -0.16, -0.11, -0.07, null],
  ["4755", "楽天グループ", "GAP_DOWN,RANGE_VERY_LARGE,BODY_LONG,DIR_BEAR", 1.2, -1.4, -0.38, -0.41, -0.18, -0.06, -0.24, -0.2, "携帯事業の資金調達観測"],
  ["7974", "任天堂", "RANGE_SMALL,WICK_UPPER_PRESENT,BODY_SMALL,DIR_BEAR", 0.9, -1.1, -0.29, -0.32, -0.24, 0.07, 0.18, -0.12, null],
];

function businessDates(asOf, count) {
  const dates = [];
  const date = new Date(`${asOf}T00:00:00Z`);
  while (dates.length < count) {
    const day = date.getUTCDay();
    if (day !== 0 && day !== 6) dates.unshift(date.toISOString().slice(0, 10));
    date.setUTCDate(date.getUTCDate() - 1);
  }
  return dates;
}

function metricSeries(end, index, length, scale = 1) {
  return Array.from({ length }, (_, point) => {
    const progress = point / Math.max(1, length - 1);
    const trend = end * (0.36 + progress * 0.64);
    const wave = Math.sin(point * 0.3 + index * 0.72) * 0.08 * scale;
    return Number((trend + wave).toFixed(4));
  });
}

function makeBundle(asOf, benchmark) {
  const axisDates = businessDates(asOf, 60);
  const adjustment = benchmark === "nikkei" ? -0.07 : 0;
  const rows = COMPANIES.map((company) => {
    const [code, name, candleLabels, z, accelZ, accel, rs31, rs63, rs126, rs252, sma75, news] =
      company;
    const kabutanBase = `https://kabutan.jp/stock/?code=${code}`;
    const newsBundle = news
      ? (Array.isArray(news) ? news : [news]).map((title) => ({
          title,
          url: `https://kabutan.jp/stock/news?code=${code}`,
        }))
      : [{ title: "材料不明・需給起因疑い", url: null }];
    const legacyNewsFields = Object.fromEntries(
      newsBundle.flatMap((item, index) => {
        const position = index + 1;
        return [
          [`event_news_${position}_title`, item.title],
          [`event_news_${position}_url`, item.url],
        ];
      }),
    );
    return {
      code,
      name,
      candle_labels: candleLabels,
      price_text: "BUNDLE_PRICE_TEXT_UNUSED",
      z_turnover_60: z,
      rs_acceleration_zscore: Number((accelZ + adjustment).toFixed(2)),
      rs_acceleration: Number((accel + adjustment).toFixed(2)),
      rs31: Number((rs31 + adjustment).toFixed(2)),
      rs63: Number((rs63 + adjustment).toFixed(2)),
      rs126: Number((rs126 + adjustment).toFixed(2)),
      rs252: Number((rs252 + adjustment).toFixed(2)),
      rs_sma75: Number((sma75 + adjustment).toFixed(2)),
      event_news_bundle: newsBundle,
      ...legacyNewsFields,
      research_prompt_block: `${code} ${name}：売買代金急増と相対強度の背景を調査`,
      link_kabutan: kabutanBase,
      link_kabutan_chart: `https://kabutan.jp/stock/chart?code=${code}`,
      link_kabutan_news: `https://kabutan.jp/stock/news?code=${code}`,
    };
  });

  const series = Object.fromEntries(
    rows.map((row, index) => {
      const values = {
        z_turnover_60: metricSeries(row.z_turnover_60, index, axisDates.length, 5),
        rs31: metricSeries(row.rs31, index, axisDates.length),
        rs63: metricSeries(row.rs63, index + 1, axisDates.length),
        rs126: metricSeries(row.rs126, index + 2, axisDates.length),
        rs252: metricSeries(row.rs252, index + 3, axisDates.length),
        rs_sma75: metricSeries(row.rs_sma75, index + 4, axisDates.length),
        rs_acceleration: metricSeries(row.rs_acceleration, index + 5, axisDates.length),
        rs_acceleration_zscore: metricSeries(
          row.rs_acceleration_zscore,
          index + 6,
          axisDates.length,
          2,
        ),
      };
      return [row.code, values];
    }),
  );

  return {
    schema_id: "stockradar.web_ui.bundle.v1",
    as_of: asOf,
    benchmark,
    metric_set_version_id: "web-ui-v1",
    set_fingerprint: "local-evaluation-prototype",
    axis_dates: axisDates,
    csv_source: "independent local evaluation data",
    rows,
    series,
  };
}

function jsonResponse(value, init = {}) {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: { "Content-Type": "application/json; charset=utf-8", ...(init.headers || {}) },
  });
}

let preferences = {};
try {
  preferences = JSON.parse(localStorage.getItem("stockradar-prototype-preferences") || "{}");
} catch {
  preferences = {};
}

const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  const method = String(init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();

  if (url.origin === window.location.origin && url.pathname === "/v1/dates") {
    return jsonResponse({ dates: PROTOTYPE_DATES, default: PROTOTYPE_DATES[0] });
  }

  if (url.origin === window.location.origin && url.pathname === "/v1/preferences") {
    if (method === "PATCH") {
      const payload = JSON.parse(String(init.body || "{}"));
      const patch = payload.bag && typeof payload.bag === "object" ? payload.bag : {};
      const merged = { ...preferences };
      for (const [ns, value] of Object.entries(patch)) {
        if (value && typeof value === "object" && !Array.isArray(value) && merged[ns] && typeof merged[ns] === "object") {
          merged[ns] = { ...merged[ns], ...value };
        } else {
          merged[ns] = value;
        }
      }
      preferences = merged;
      localStorage.setItem("stockradar-prototype-preferences", JSON.stringify(preferences));
    }
    return jsonResponse({ bag: preferences });
  }

  if (url.origin === window.location.origin && url.pathname === "/v1/mint") {
    const payload = JSON.parse(String(init.body || "{}"));
    const bundleUrl = new URL("/mock/bundle", window.location.origin);
    bundleUrl.searchParams.set("as_of", payload.as_of || PROTOTYPE_DATES[0]);
    bundleUrl.searchParams.set("benchmark", payload.benchmark || "topix");
    return jsonResponse({ signed_url: bundleUrl.href });
  }

  if (url.origin === window.location.origin && url.pathname === "/mock/bundle") {
    const asOf = url.searchParams.get("as_of") || PROTOTYPE_DATES[0];
    const benchmark = url.searchParams.get("benchmark") === "nikkei" ? "nikkei" : "topix";
    return jsonResponse(makeBundle(asOf, benchmark));
  }

  return nativeFetch(input, init);
};

function element(id) {
  return document.getElementById(id);
}

window.__webUiProgress = {
  show(label, ratio) {
    const root = element("boot-progress");
    const bar = element("boot-progress-bar");
    const text = element("boot-progress-label");
    if (root) {
      root.hidden = false;
      root.setAttribute("aria-busy", "true");
    }
    if (text && label) text.textContent = label;
    if (bar && Number.isFinite(ratio)) {
      const percent = Math.max(4, Math.min(100, Math.round(ratio * 100)));
      bar.classList.remove("is-indeterminate");
      bar.style.width = `${percent}%`;
      bar.setAttribute("aria-valuenow", String(percent));
    }
  },
  hide() {
    const root = element("boot-progress");
    if (root) {
      root.hidden = true;
      root.setAttribute("aria-busy", "false");
    }
  },
};

window.__WEB_UI_CTX = {
  bffOrigin: window.location.origin,
  accessToken: "local-evaluation-only",
  uid: "operator",
  role: "operator",
};

window.__webUiLogout = async function webUiLogout() {
  window.__WEB_UI_CTX = null;
  const app = element("app-root");
  if (app) app.hidden = true;
  const shell = element("login-shell");
  if (shell) shell.hidden = false;
  const form = element("form");
  if (form) form.hidden = false;
  const loginCopy = element("t5-login");
  if (loginCopy) loginCopy.hidden = false;
};

await window.__webUiBoot();
