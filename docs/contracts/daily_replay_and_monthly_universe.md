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

## Patched cache (Actions cache)

### Key format (machine-selectable)

- Writer (`daily_universe_patch.yml` only):  
  `universe-patched-${MONTHLY_TAG}-${RUN_DATE}`  
  where `RUN_DATE` is `YYYY-MM-DD` (trading anchor from `resolve_trading_day`).
- **Suffix must be** `-YYYY-MM-DD` at the end so `daily.yml` can parse `MONTHLY_TAG` + patch date from the key.
- Reader (`daily.yml` → `resolve_core_csv`): **restore only**. No `actions/cache/save` for patched cache in `daily.yml`.

### Selection algorithm (`resolve_core_csv`)

1. List cache keys via GitHub API (paginated).
2. Filter keys matching `universe-patched-${MONTHLY_TAG}-*` and parse trailing date.
3. Keep keys in the **same calendar month** as `run_date`, with patch date **<= run_date** (inclusive).
4. Pick the **latest** patch date (nearest on or before `run_date`). If none → **monthly fallback**.

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

- **Universe**: `daily.yml` does **not** run `patch_universe_daily`. Core CSV is **only** from `resolve_core_csv` artifacts.
- **Run artifacts** (short-lived, `retention-days: 3` where applicable):
  - `daily-core-csv-${GITHUB_RUN_ID}` — `equity_domestic_core_with_name.csv`
  - `daily-core-quality-${GITHUB_RUN_ID}` — `core_selection.json`
  - `daily-ohlc-store-${GITHUB_RUN_ID}` — `ohlc_store.zip`
  - `daily-index-store-${GITHUB_RUN_ID}` — `index_store.zip`
- **Warm caches** (fixed keys, sole writers in this workflow):
  - OHLC: `ohlc-store-zip-v2` — **only** `ensure_core_cache` (after `archive_ohlc_store`, delete key, save).
  - Index: `index-store-zip-v1` — **only** `ensure_index_cache` (after `archive_index_store`, delete key, save).
- **`compute_indicators`**: consumes **only** the above artifacts (plus optional stale exclusions). **No** `actions/cache/save` for OHLC/index in this job.
- **Replay**: `is_replay=true` ではウォーム用の **`actions/cache/save` をスキップ**し、既存キー削除は `python -m stockradar.jobs.cache_ops rotate-delete` が内部的に no-op になる（restore は従来どおり可）。無条件の `gh cache delete` 相当は `delete-key` サブコマンド。

### `actions/cache/save` count (this workflow only)

Exactly **two** saves on a normal successful run: index zip + OHLC zip.  
(`daily_universe_patch.yml` patched-cache save is a **separate** workflow.)

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
