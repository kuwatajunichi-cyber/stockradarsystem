# Phase 2c R2-only cutover runbook

Issue #93 Phase 2c: remove GitHub artifact upload/download from the daily run-internal artifact bus; R2 staging + `run_artifact` manifest is the sole handoff.

Related contract: [github_state_to_r2_supabase_mapping.md](../contracts/github_state_to_r2_supabase_mapping.md)

## Prerequisites (completed)

- [x] FI-1 live run #175 (`handoff_source=github_fallback` on required consumers)
- [x] Optional FI-1P live run #176 (producer degraded visibility)
- [x] Post-gate normal run #179 (`handoff_source=r2`, publish success)
- [x] Phase 2c promotion gate cleared (Issue #93 comment 2026-06-29)
- [x] Phase 2c merge (PR #104, `dcb0d62`, 2026-06-29)
- [x] Post-merge live run #180 (2026-06-30, R2-only handoff + publish success)

## Live gate status

**Phase 2c live gate: CLOSED** (2026-06-30). Post-merge verification run #180 satisfies the checklist below. Phase 2 (daily run-internal artifact bus) is complete; Phase 3 (`artifact_index`, warm cache) may proceed per [github_state_to_r2_supabase_mapping.md](../contracts/github_state_to_r2_supabase_mapping.md).

## Scope

**In scope (7 entry ids):**

- `artifact-daily-core-csv`, `artifact-daily-core-quality`, `artifact-daily-index-store`, `artifact-daily-ohlc-store`
- `artifact-stale-exclusions` (optional), `artifact-daily-indicators`, `artifact-enriched-csv` (optional)

**Out of scope:**

- `actions/cache` warm cache (index/OHLC/patched universe)
- `monthly.yml` GitHub Release
- `scripts/upload_to_all_targets.py` customer publish
- Supabase `artifact_index` commit (Phase 3)

## Merge gate (CI)

Before merge:

1. `pytest --strict-markers -m "unit or job_integration or smoke"` passes (no Secrets)
2. `reusable_quality_gate.yml` / actionlint green on PR

## Post-merge live verification

On the **first trading day** after Phase 2c merge (Cloudflare Cron or manual `workflow_dispatch` with `skip_publish=false`):

| Job | Expected |
|-----|----------|
| `resolve_core_csv` | producer `r2_put_ok=true`, manifest keys in outputs |
| `ensure_index_cache` | producer `r2_put_ok=true` |
| `ensure_core_cache` | consumer `handoff_source=r2`; producer `r2_put_ok=true` |
| `compute_indicators` | all required consumers `handoff_source=r2`; producer indicators `r2_put_ok=true` |
| `event_cause_enrichment` | consumer indicators `handoff_source=r2`; producer enriched `r2_put_ok=true` |
| `render_and_upload` | consumers `handoff_source=r2`; **Upload to all targets success** |

**Must not appear in summaries:**

- `handoff_source=github_fallback`
- `fallback_used`
- `handoff_failed`
- `producer_degraded`

### Post-merge live verification record (2026-06-30)

| Item | Value |
|------|-------|
| Run | Daily Indicators **#180** |
| URL | https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28425706867 |
| Result | workflow **success** (~14 min) |
| Merge commit | `dcb0d625` (PR #104 Phase 2c) |
| Trigger | Cloudflare Cron dispatch (`workflow_dispatch`, 06:45 UTC) |
| Inputs | `run_date` empty, `skip_publish=false`, `is_replay=false` |
| Resolved | `run_date=2026-06-30`, `is_open=True` |

**Verified:**

- No `validate_fault_injection` job; no GitHub artifact upload/download or fallback steps (R2-only workflow)
- Required producers: `r2_put_ok=true` for core CSV/quality, index store, OHLC store, indicators, enriched CSV
- Required consumers: `handoff_source=r2` on `ensure_core_cache`, `compute_indicators`, `event_cause_enrichment`, `render_and_upload`
- Optional `artifact-stale-exclusions`: `skipped_optional_missing` (`stale=0`; contract-compliant)
- `Upload to all targets` **success** (`upload_status=ok`)
- No `handoff_failed`, `producer_degraded`, or live-path `github_fallback` in job logs

Recorded in Issue #93 (2026-06-30 comment).

## Rollback

1. Revert merge commit to Phase 2b (GitHub artifact fallback restored)
2. Confirm next trading day live run per Phase 2b contract (`handoff_source=r2` or `github_fallback`)
3. Do not delete R2 staging objects manually; `runs_staging_cleanup.py --keep-days 14` handles retention

See [cloudflare_github_cron.md](cloudflare_github_cron.md) Phase 2c rollback note.
