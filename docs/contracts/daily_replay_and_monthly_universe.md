# Daily replay and monthly universe (contract)

Japanese summary: README and workflow comments describe operator-facing behavior.

## Definitions

- Normal run: schedule, or dispatch with empty run_date, or run_date equals Tokyo today.
- Replay run: dispatch with run_date not equal to Tokyo today.
- Replay window: run_date within last 3 calendar months from Tokyo today.

## Monthly selection

- Tags: `monthly-YYYYMMDD-<github.run_id>`. Max snapshot D with D <= run_date; tie-break max run_id.
- If none: first parsable `monthly-*` from gh release list order; `universe_resolution=fallback_latest`.
- **Both** `daily.yml` (`resolve_core_csv select`) and `daily_universe_patch.yml` use
  `resolve_monthly_release_for_run_date` / `pick_monthly_release` so **MONTHLY_TAG is identical** between
  patched cache writer and reader.

## Patched universe cache (Phase 3c: R2 + Supabase)

### Key format (machine-selectable)

- Writer (`daily_universe_patch.yml` only):  
  `universe-patched-${MONTHLY_TAG}-${RUN_DATE}`  
  where `RUN_DATE` is `YYYY-MM-DD` (trading anchor from `resolve_trading_day`).
- **Suffix must be** `-YYYY-MM-DD` at the end so `daily.yml` can parse `MONTHLY_TAG` + patch date from the key.
- Writer persists via `cache_bus_cli put-patched` → R2 `cache/universe-patched/...` + Supabase `cache_index`.
- Reader (`daily.yml` → `resolve_core_csv`): **restore only** via `get-patched`. No patched cache write in `daily.yml`.

### Selection algorithm (`resolve_core_csv`, Phase 3c)

1. List patched rows from Supabase `cache_index` (filtered by allowed `source_ref`).
2. Filter keys matching `universe-patched-${MONTHLY_TAG}-*` and parse trailing date.
3. Keep keys in the **same calendar month** as `run_date`, with patch date **<= run_date** (inclusive).
4. Pick the **latest** patch date (nearest on or before `run_date`). If none → **monthly fallback**.

Scheduled patch launch: Cloudflare Cron `0 3 * * *` UTC (12:00 JST) → Worker → `workflow_dispatch`  
(daily launch: `45 6 * * *` UTC / 15:45 JST). See `docs/contracts/daily_universe_patch_cloudflare_cron_dispatch.md`.

### Monthly fallback quality contract

When no patched cache candidate exists, `resolve_core_csv materialize` downloads the monthly release CSV as-is.

Machine-readable `core_selection.json` (artifact `daily-core-quality-*`) **must** include:

- `core_source=monthly_fallback`
- `delisted_patch_applied=false`
- `quality_tier=degraded_without_delisted_patch`
- `MONTHLY_TAG`, `run_date`, `universe_resolution`, `resolution_reason`

When patched cache is used:

- `core_source=patched_cache`
- `delisted_patch_applied=true`
- `quality_tier=full`
- `selected_cache_key` set to the restored cache key
- `MONTHLY_TAG`, `run_date`, `universe_resolution`, `resolution_reason` (same schema as fallback)

## `daily.yml` (Daily Indicators) data flow

- **Universe**: `daily.yml` does **not** run `patch_universe_daily`. Core CSV is **only** from `resolve_core_csv` → R2 staging artifacts.
- **Run artifacts** (R2 `runs/daily/{run_id}/...`, Phase 2c+):
  - core CSV, core quality JSON, OHLC zip, index zip, indicators CSV, enriched CSV (optional)
- **Warm caches** (Phase 3c: R2 `cache/` + Supabase `cache_pointers`; no `actions/cache`):
  - OHLC: `cache-ohlc-store-zip-v2` — `ensure_core_cache` (`get-fixed` / `put-fixed`)
  - Index: `cache-index-store-zip-v1` — `ensure_index_cache` (`get-fixed` / `put-fixed`)
- **`compute_indicators`**: consumes R2 handoff artifacts (plus optional stale exclusions). No warm cache write in this job.
- **Replay**: `is_replay=true` skips warm cache **pointer update** (`put-fixed` / `put-patched` idempotent skip). R2 run staging handoff unchanged.

### Phase 4.5 planned derived-series behavior

- Normal run: committed daily derived snapshot から R2 Web series projection と Supabase latest projection を更新する。
- Replay: run scope の派生計算・比較は許可するが、shared `derived-snapshots/`、`derived-series/`、Supabase latest projection、active metric set を更新しない。
- Backfill: `draft` / `shadow` metric set のみ更新し、active set と latest projection を更新しない。
- Reconcile: replay / backfill と別 entrypoint とし、expected old logical digest と変更理由を必須にする。

詳細は `docs/adr/adr-004-derived-indicators-warm-cache.md` を参照する。Phase 4.5 は設計済み・未実装であり、この節は現行 workflow が既に派生系列を更新することを意味しない。

### Warm cache writes (Phase 3c)

On a normal successful run, index + OHLC warm cache commits occur via `cache_bus_cli put-fixed` when incremental ensure jobs produce new zip bodies.  
(`daily_universe_patch.yml` patched-cache write is a **separate** workflow.)

## Short-lived artifact cleanup

- `cleanup_artifacts.yml` は `scripts/cleanup_artifacts.py` と `config/cleanup_artifacts.yaml` のルールで、`daily-core-*` / `daily-index-store-*` 等の短命 artifact を prefix 単位で削除する（本契約の命名と整合）。

## Publish

- Default publish; `skip_publish=true` on dispatch skips render/upload.

## Code

- `src/stockradar/universe/monthly_release_pick.py`
- `src/stockradar/jobs/validate_daily_dispatch_run_date.py`
- `src/stockradar/jobs/resolve_monthly_release_for_run_date.py`
- `src/stockradar/jobs/core_csv_selection.py`
- `src/stockradar/jobs/resolve_core_csv.py`
- `src/stockradar/jobs/cache_ops.py`

## Downstream compatibility

- `daily_event_cause_enrichment.yml` continues to download `daily-indicators-${run_date}` from `compute_indicators`; that artifact name is unchanged.
