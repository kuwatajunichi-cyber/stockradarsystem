# Track D Web UI first version (screen SSOT)

**Adopt token:** `web_ui_v1`
**Status:** First-version screen spec **adopted** (2026-09-22). Bundle JSON Schema, host, CORS, and live evidence keys added 2026-10-02. Implementation, Auth, mint, and distribution cutover are not completed by this file.
**Gates:** [phase5_gate_status.yaml](../operations/phase5_gate_status.yaml) `pr-5d-web-ui` is **pending**. `live_gate_5d` is **open**. Phase 5 `overall_status` is **in_progress**. Issue #93 is **OPEN**. Do not write Web UI complete.
**Source:** localhost prototype `prototypes/web-ui-asof/` and [phase5_product_spec_requirements.md](../operations/phase5_product_spec_requirements.md) 2026-09-22 capture. Prototype is not live evidence.
**Metrics:** Adopt `rs_sma75_topix` / `rs_sma75_nikkei` into production metrics. First-live **active** catalog is `config/metrics/metric_set_v1_1.yaml` (full 23). `metric_set_v1_1_free.yaml` is later free-role only. **Do not CAS active pointer / switch daily writer in this file** (ADR-004 draft to shadow to active). Ops CAS is outside this file. `live_gate_5d` stays open.

Do not overturn: no investment advice / trade signals. Delivery is private R2 + committed only + short-lived GetObject. allow-stub forbidden. Public mint = unauthenticated signing. Forbidden. Authenticated BFF is Track C/D. No ListObjects on the normal path.

Japanese summary (normative with English tokens above):

- 調査候補の横断表 + 銘柄単位60営業日グラフ + WEBペイン。助言禁止。
- 母集団は equity_domestic_core。4ロール。初回 live 対象は運用者+内部β（T-4）。ホストは T-1 案 C（Workers Static Assets 静的 UI + 別ホスト認証必須 BFF）。外部有料/無料は種別のみ。無料の行絞りはサーバ側（初回はそのロールを出さない）。
- レイアウト: 左上表 / 左下WEB（スプリッタ） / 右グラフ。as-ofは日付プルダウン。date列なし。表とグラフは同一集合・同一順。ホバー/選択同期。
- 表デフォルト: コード, 銘柄名, お気に入り, price_text, Zscore, 加速Z, 加速, RS31/63/126/252, SMA75 RS, ニュース候補束ね, 調査ブロック。株探3リンクはWEBタブ。Web 表の条件付き書式は試作仕様（色相と価格ピル）。XLSX 端点色は成果物側に残す。価格挙動セルの文言は `candle_labels` からクライアントが合成する（辞書 `assets/price-text.js`。初期値は Excel `price_text` と同じ構文）。バンドルに `price_text` があってもラベルがあれば使わない。`price_text` はラベル欠落時のフォールバックのみ。
- グラフ: y_RS=RS, y_Z=z/5, 既定窓[-1,1], クリップしない。パンは[-2,+5]で離すと復帰。はみ出し縁（RS色、ZのみはZ色）。
- WEB: 既定=株探3+ニュース候補一括。材料不明はテキスト。バフェット/みんかぶ/YahooはデフォルトOFF。iframe拒否は別タブ。プロキシしない。
- rs_sma75: SMA75系列の31日B方式RS。metric_set_v1_1 draft。v1 in-place変更禁止。
- ホスト: T-1 案 C。実装は Workers Static Assets (`web-ui-static`) + 別 Worker BFF (`web-ui-bff`)。セッションは Supabase Auth。JWT は `Authorization: Bearer`。T-6 は auth.uid。
- mint キー: T-2 案 C。as_of + benchmark。derived-web-asof/ をベンチ別。ニュースは as-of 揃え。SMA75 空列禁止。顧客正本は XLSX。
- 失敗画面 T-5: 未ログインはログインへ。利用不可は stub しない。API 死はログインへ送らない。署名 URL を出さない。
- Track D は製品範囲。MVP の UI 禁止は撤回。助言禁止は残す。
- 表層: Web Awesome 3.14.0。実行時 CDN 禁止。評価プロトタイプ `prototypes/web-ui-webawesome/` は live 証拠ではない。
- 本ファイルでやらない: Auth/mint実装, v1 in-place, pr-5d merged_and_verified, live_gate_5d close, overall close, プロトを本番宣言。

## Users (D-1)

Same app, four roles. Universe = equity_domestic_core only.

| Role | First-version live | Screen |
|------|--------------------|--------|
| operator | in scope (T-1 case C: static UI + BFF) | full |
| internal_beta | in scope | full |
| external_paid | role reserved; not first live | same as beta |
| external_free | role reserved; not first live | same metric kinds; z_turnover_60 desc through 20th-place ties; no sort change; no favorites |

Free-row cap is **server-side**. Client "free preview" is demo-only.

## Screen (D-2 / D-8 / D-9 / D-10 / D-11 / D-12 / D-13 / D-14)

Three panes: table (top-left), WEB (bottom-left, splitter), per-name charts (right). Benchmark TOPIX/Nikkei toggle, not simultaneous.

Default table columns: code, name, favorite, price_text, Zscore, accel Z, accel, RS31/63/126/252, SMA75 RS, news-candidate bundle, research block. Kabutan three links move to WEB tabs. Numeric `+0.0`/`+/-0`. The price-text column is composed on the client from `candle_labels` (`assets/price-text.js`; starting copy matches Excel `price_text`). If a row has `candle_labels`, bundle `price_text` is ignored. Bundle `price_text` is fallback only when labels are missing.

Web table conditional format is the evaluation prototype (not XLSX endpoint fills). Numeric cells: range 5 for Zscore/accelZ, range 1 for accel/RS/SMA75; positive `hsl(156 58% 48%)`, negative `hsl(346 72% 58%)`; background alpha `0.08 + intensity * 0.2`; text mixed 62% toward `--fg`. Price-text is a pill: positive for 陽線/S高, negative for 陰線/S安, otherwise muted. XLSX workbook endpoint colors stay unchanged.

Charts overlay RS31/63/126/252, SMA75 RS, z_turnover_60. Display-only `y_RS=RS`, `y_Z=z/5`. Shared axis default **[-1,+1]**. No autoscale. No clamp. Hover shows raw. Drag-pan world **[-2,+5]**, release snaps to 0. Overflow edges: top green / bottom red (RS31); Z-only overflow uses Z color. End Z bars stay in plot.

WEB default tabs: Kabutan overview/chart/news + news candidates (10-char labels, one switch). Unknown-material is text not tabs. Buffett / Minkabu / Yahoo default OFF. iframe then new tab. No proxy.

Favorites are named lists in one table column (T-6): bag `favorites.lists` is SSOT (max 12; name ≤20 chars; ≤500 codes/list; ≥1 list). `favorites.codes` is the union for older clients. A cell shows up to 5 membership chips on two rows (`+N` after that) and opens a save flyout (toggle lists; create list with the current code). List CRUD and members live in an account-menu modal. Column header filter is a `wa-dropdown` checkbox list (Excel-style: すべて / 空白 / each non-empty list with counts; chip left of the label; OR). `favorites.include_blank` round-trips with `filter_ids`. Free role cannot write favorites. Unknown keys round-trip, namespace-level merge, 64KiB cap. Header numeric sort/filter and "all RS negative exclude" exist; disabled for free role. Shared y-axis is not permanently expanded (T-7). `turnover_yen` stays out of the column panel (T-8).

Daily XLSX remains the customer canonical for now (T-3 / E-4). Web is an extra view. Host is T-1 case C (Workers Static Assets + authenticated BFF Worker, Supabase Auth, `auth.uid`). Mint keys are `as_of`+`benchmark` into `derived-web-asof/` (T-2 case C). First live: browser direct GetObject. Free later: BFF proxy. Failure copy is T-5 (login vs unavailable vs temporary; never show signed URLs). `published/` cutover is after internal Web live. No operator infra tab (T-10). No public mint; no user RLS on first live; no billing webhook until external paid (T-9).

## Surface library

Chrome controls are **Web Awesome 3.14.0** custom elements, bundled into Workers Static Assets. No runtime CDN. `html` uses `wa-dark`. Tokens: brand `#4da5ee`, `--fg: #e8f1f7`, `--surface-raised: #0d1924`, chart canvas `--chart-bg: color-mix(in oklab, var(--wa-color-gray-05), black 20%)`. Banner, toolbar, legend bar, chart pane, and Kabutan pane use `--surface-raised`. Legend tag bodies use `--chart-bg`. Chart title code/name match table body font (family, size, weight 400, line-height, `--fg`). Japanese fallback on the family token: `Yu Gothic UI`, `Meiryo`. Spectrum / UI5 / Vaadin / Lion are evaluation-only.

This section does not merge `pr-5d-web-ui`, close `live_gate_5d`, or mark Web UI complete. Phase 5 `overall_status` stays **in_progress**. Issue #93 stays **OPEN**. The localhost prototype is not production and is not live evidence.

## Read path (D-3 / T-2 case C)

Mint keys are **`as_of` + `benchmark`**. Prefix `derived-web-asof/` (one object per bench; do not fetch both benches together). Dates list and T-6 are other APIs. Writer SSOT for series remains ADR-004 `derived-series/`. The bundle is a regenerable Web projection. News/links/research sit in the same as-of bundle (no calendar drift). No ListObjects. Client does not build `object_key`. First live must not show empty SMA75 columns: `metric_set_v1_1` must be **active** first (this file does not CAS).

Machine schema: [web_asof_bundle.schema.json](web_asof_bundle.schema.json). Token `web_asof_bundle_v1`. Pure validator: `stockradar.storage.web_asof_bundle`.

## View bundle JSON (`web_asof_bundle_v1`)

One as-of × one bench = table last-bar + 60-session series. Object key:

`derived-web-asof/metric-set={uuid}/benchmark={topix|nikkei}/as-of={YYYY-MM-DD}/bundle.json.gz`

**Encoding:** the R2 object is gzip of UTF-8 JSON. The client **must gunzip** then parse. Do not rely on HTTP `Content-Encoding`. After gunzip, treat the payload as `Content-Type: application/json`. gzip object size **< 8 MiB** (`GZIP_MAX_BYTES`).

**Required top-level keys:** `schema_id` (`web_asof_bundle_v1`), `as_of`, `benchmark` (`topix`|`nikkei`), `metric_set_version_id`, `set_fingerprint` (64 hex), `axis_dates` (length 60, last element = `as_of`), `rows`, `series`.

**Row identity:** `code` (4-character JPX ticker: digits and/or A-Z), `name`. Optional: `price_text`, `event_news_bundle`, `research_prompt_block`, `candle_labels`, `link_kabutan`, `link_kabutan_chart`, `link_kabutan_news`, `link_buffett`, `link_minkabu`, `link_yahoo`. Web table price-behavior copy is composed from `candle_labels` even when `price_text` is also present; `price_text` remains for Excel/CSV and as a client fallback only when labels are missing.

**Per-bench numeric keys (unsuffixed; the object is already one bench):** `z_turnover_60`, `rs_acceleration`, `rs_acceleration_zscore`, `rs31`, `rs63`, `rs126`, `rs252`, `rs_sma75`. Type: number or null. The `rs_sma75` **column must exist** on every row (empty column forbidden). Null is allowed only for lookback-short names.

**Series:** `series[code][metric]` is length 60, aligned to `axis_dates`. Last bar must equal the row value. `series` keys must equal the set of `row.code`.

**News:** taken from the same as-of enriched CSV. Missing news is null + visible; do not copy the previous as-of.

## Daily bundle failure (`bundle_failure_fails_daily`)

If the web-asof projection job fails, **the daily workflow is failed**. Derived snapshot/series **commit is not rolled back**. Re-run rebuilds the projection only.

## Host and Auth (D-4 / C-1 / T-1 case C)

T-1 case C = static UI + a **separate** authenticated BFF. Implementation: Cloudflare **Workers Static Assets** (`web-ui-static`) plus BFF Worker (`web-ui-bff`). Not a new Pages project. JWT on the first live is **`Authorization: Bearer`** (sibling `workers.dev` hosts cannot share cookies). Session is Supabase Auth (ADR-003). Public mint = unauthenticated signing; forbidden. Authenticated BFF is Track C/D.

BFF CORS: allowlist the verified static origin only (no wildcard). Methods POST/PATCH plus OPTIONS preflight. Allow headers `Authorization` and `Content-Type`. `Vary: Origin`. Unauthenticated mint is 401.

First live (operator / internal_beta; later paid): BFF returns a short-lived GetObject URL; the browser reads R2 on the S3 API host. Do not proxy the paid/internal path. Free role (later live): BFF fetches the bundle and applies the row cap (proxy). Browser must not call PostgREST; BFF uses `service_role` for T-6.

R2 CORS: allow the static origin for GET / HEAD / OPTIONS only. No PUT/DELETE. Bucket stays private. Exact origin URL is an implementation PR. This file does not deploy Worker/Auth/CORS.

## Failure copy (C-6 / T-5)

Unauthenticated / 401 → login. `unproven` / expired / `identity_mismatch` / 403 → 「利用できません」 (re-login allowed; no stub data). Static origin up but API down / 5xx / CORS fail → 「一時的に利用できません」 (do **not** bounce to login). Never render signed URL or object_key.

## rs_sma75 production metrics

Not close RS75. SMA75 series (name + bench) then B-method RS window 31. Keys `rs_sma75_topix` / `rs_sma75_nikkei` in the catalog; unsuffixed `rs_sma75` inside a per-bench bundle. Lookback-missing names may be null; the SMA75 columns themselves must exist in the first-live bundle. Catalog family `daily_core_v1_1`. Do not mutate metric_set_v1 in place. Pure must match `src/stockradar/prototype_web_ui_asof/sma75_rs.py`. This file does not start daily/monthly.

CAS gate (numeric, token `SMA75_NON_NULL_RATE_MIN`): among names with at least 105 trading days of close on stock and bench as of that as-of, `rs_sma75` non-null rate must be **>= 0.98**. Denominator 0 or all-null is CAS-forbidden. This file does not CAS.

## MVP (D-7)

Phase 5 Track D Web UI is in product scope. MVP section 2.2 no-UI policy is withdrawn (MVPdesignDoc_v1.2 section 2.3). Advice ban remains. This file does not complete live Web UI.

## Out of first version (still undecided)

Exact static origin URL for R2 CORS AllowedOrigins. Comparison archive: [phase5_product_spec_requirements.md](../operations/phase5_product_spec_requirements.md)

## Must not

- Implement Auth / mint / Worker deploy from this file
- In-place metric_set_v1 change or active CAS
- Mark `pr-5d-web-ui` merged_and_verified without merge evidence
- Close `live_gate_5d`
- Close Phase 5 overall or Issue #93
- Call the localhost prototype production
