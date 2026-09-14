# Daily derived / publish pooler 504 recovery

Incident: 2026-09-14 (XTKS open). This document does not close Phase 5 / Issue #93.

Prevention SSOT on main: daily.yml write_derived_generation serialization and series_provenance_for_run_mode (PR #179). This page is the incident recovery SSOT.

## What broke

write_derived_generation RPCs and render_and_upload publish_status REST hit the Supabase pooler together. One of the two 504s. This is not slow SQL. One side can succeed while the other is missing.

Failed generations leave derived_object_index.status=orphan and bloat the unique index. Weekly supabase_orphan_sweep.yml does not cover derived_object_index.

## Prevention (code / CI)

| Failure | Mitigation | Test |
|---|---|---|
| Concurrent 504 | derived starts after render_and_upload finishes. always() and compute success; render must not be cancelled. Publish failure still writes derived | tests/test_phase45_cutover_workflow_contract.py |
| reconcile / backfill provenance | series_provenance_for_run_mode. replay and unknown modes fail-fast | tests/test_phase45_canonical_writer_contract.py |

Do not re-run full daily.yml on a SHA that lacks this serialize.

## Detection

1. Which daily.yml job is failure / skipped (render_and_upload vs write_derived_generation vs finalize_run).
2. Healthchecks daily ping fires on render success. Derived can fail later: ping sent, runs.status=failed.
3. publish_status committed rows for the day, derived_generation_runs latest committed, latest_derived_observations count.

## Recovery branches

Same Tokyo calendar day and not replay: workflow_dispatch daily.yml with empty run_date. concurrency daily-indicators has cancel-in-progress false. Wait if a run is already active.

| State | Action |
|---|---|
| Failed on a SHA without serialize | Land PR #179 equivalent on main first. Do not re-dispatch full daily on unserialized main |
| Publish missing, derived ok | Empty run_date daily. Render fills publish. Derived runs after render completes (new generation) |
| Publish committed, derived missing | Empty run_date daily is enough. To write derived only: derived_reconcile.yml (trade_date, metric_set_version_id, snapshot_r2_key, expected_old_digest). CI fixture forbidden |
| Both missing | Empty run_date daily. Confirm compute artifacts exist on the same-run artifact bus |
| Failed generation orphans | Sweep below. Never delete committed / superseded / pending |

GitHub Re-run of the same github_run_id is rejected by begin_derived_generation. Always a new workflow_dispatch.

## Orphan sweep (safety)

scripts/storage/derived_generation_sweeper.py and .github/workflows/derived_orphan_sweep.yml.

1. dry_run is the default. Dispatch derived_orphan_sweep.yml with dry_run=true first.
2. R2 prefix-delete only orphan-only generations. If the generation has any committed / superseded / pending row, it is mixed: no prefix. If latest_derived_observations points at the generation_id, no prefix.
3. Mixed: delete only orphan object_keys that are not in the global committed key set. Never derived-inputs/.
4. mark_orphan_object_purged sets purged_at and does not delete the row. Unique-index bloat needs a physical DELETE.
5. Physical DELETE is RPC delete_orphan_derived_objects (migration 020_delete_orphan_derived_objects.sql). status=orphan only. Set delete_orphan_rows=true after 020 is applied in production.
6. After a large DELETE, operator SQL: VACUUM (ANALYZE) public.derived_object_index. REINDEX TABLE CONCURRENTLY if needed. Not from GHA.
7. Verify: orphan count 0, committed count unchanged, latest generation and observation count as intended.

Do not extend weekly orphan_sweeper.py to derived. The rules differ.

## Do not

- Prefix-delete derived-snapshots/.../generation={id}/ or derived-series/.../generation={id}/ on mixed generations
- DELETE rows whose status is committed, superseded, or pending
- Re-run full daily on main before serialize, recreating the 504 race
- Close Phase 5 / Issue #93 with this procedure
