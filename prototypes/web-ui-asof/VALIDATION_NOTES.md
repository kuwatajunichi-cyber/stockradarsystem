# Validation checklist notes (not a gate close)

This memo records local checks against the as-of prototype.
It does **not** close `pr-5d-web-ui` / `live_gate_5d` / Phase 5 overall / Issue #93.

Checked at: 2026-09-13 (re-audit after XLSX parity / full-universe freeze / deep metric check)

## Data note

- 9/11 enriched CSV was not in worktree; 9/10 CSV was copied into `data/output/staging/web_ui_asof/`.
- Local `yf_index` / `yf_daily` max usable as-of after UTC-naive normalize is **2026-08-17**.
- Freeze with as-of 2026-09-10 correctly **FAIL**s (index missing as-of bar).
- Full freeze: `data/output/staging/web_ui_asof/2026-08-17.sqlite`
  - `n_rows=2194`, `n_excluded=27`, `axis_len=60`
  - Excluded = missing/stale daily cache vs CSV codes (e.g. `150A`, `2436`, …).
- **Metrics + `price_text` / candle labels** are recomputed from cache at freeze as-of.
- **Identity / Kabutan links / event news / research_prompt_block** remain from the source CSV (may be a different calendar date than as-of). Banner states this.
- Deep audit: pure indicator recompute matched freeze row+series last bar for `5010` / `7203` / `9984` / `1301` (z / rs31 / 加速 / 加速Z / rs_sma75). Null holes preserved on shared XTKS axis (e.g. `1301` has 14 null z bars).

## XLSX v1.4 parity (table)

Default columns (Web = v1.4 minus `link_buffett` plus `rs_sma75_*`):

| Order | Key | UI label |
|---|---|---|
| 1 | date | date |
| 2 | code | コード |
| 3 | name | 銘柄名 |
| 4 | link_kabutan | 概要 |
| 5 | link_kabutan_chart | チャート |
| 6 | link_kabutan_news | ニュース |
| 7 | price_text | (当日の価格挙動) |
| 8 | z_turnover_60 | Zscore |
| 9 | rs_acceleration_zscore_* | 加速Z |
| 10 | rs_acceleration_* | 加速 |
| 11–14 | rs31/63/126/252_* | 31日…252日 |
| 15–17 | event_news_{1,2,3}_title | 第一候補…第三候補 |
| 18 | research_prompt_block | 調査ブロック |
| 19 | rs_sma75_* | SMA75 RS |

Numeric cells use XLSX format `+0.0;-0.0;±0` via `fmtSigned1`.

## Chart

- Shared XTKS 60-session axis; missing symbol days stay null holes.
- Overlay: RS31/63/126/252, SMA75RS, Z/5.
- Y range fixed [-1, 1]; ticks at -1/-0.5/0/0.5/1; legend colors; no value clamp.
- Visible rows only (IntersectionObserver); bench toggle refreshes chart series.

## Browser checklist (localhost serve of full sqlite)

| Item | Result | Note |
|---|---|---|
| Banner shows as-of + not Track D | OK | provenance line included |
| Gate disclaimer in header | OK | |
| Table = XLSX default cols + JP labels | OK | 19 headers; buffett off |
| Numeric display `+0.0`/`±0` | OK | |
| All symbols with cache as-of | OK | 2194 rows |
| TOPIX / Nikkei mode | OK | remaps `_*_topix` → `_*_nikkei` |
| Column toggle | OK | |
| Free preview z-desc + ties at 20th | OK | 20 keep on this as-of (no extra ties) |
| Legend + axis ticks | OK | screenshot |
| Kabutan pane / blank tab | OK | iframe often blocked |
| Row last bar == series last bar | OK | unit + deep audit |
| Claim Track D / Web UI done | **no** | |

## Product judgment (yes/no only)

- Shared 60-day axis + null holes: **yes**
- Mode switch without refetch rows: **yes**
- Free preview sort lock: **yes**
- Kabutan iframe: **partial** (blank-tab required)
- Chart clamp: **no** (do not clamp)
- Claim Web UI / Track D done: **no**

## Gates

`docs/operations/phase5_gate_status.yaml` Track D remains **pending** / `live_gate_5d` **open**. Do not update gate status from this work.

## How to re-open

```bash
python scripts/prototype_web_ui_asof/serve.py --sqlite data/output/staging/web_ui_asof/2026-08-17.sqlite --port 8765
# http://127.0.0.1:8765/
```

## 日付切替（プロト）

- 表の `date` 列はオミット（列の出し隠しにも出さない）。as-of はツールバーの日付プルダウンで切替。
- 切替時は `/api/meta|rows|series?as_of=` を再取得し、表・グラフをその日時点で再描画。
- プロトの候補日: `2026-08-13` / `2026-08-14` / `2026-08-17`（`data/output/staging/web_ui_asof/asof/*.sqlite`）。
- 本番想定: データがある任意日付。プロトは約3日分のみ。

