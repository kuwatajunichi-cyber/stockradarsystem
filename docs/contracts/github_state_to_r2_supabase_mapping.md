# GitHub Actions state to R2 / Supabase mapping (Phase 2)

See `config/github_state_to_r2_supabase_mapping.yaml` for the machine-readable contract.

## Purpose

Defines how GitHub Actions **artifacts**, **caches**, and **Releases** map to **R2 (blob plane)** and **Supabase (control plane)** for Issue #93.

**Phase 2 scope:** daily run-internal artifact bus (`runs/daily/{run_id}/artifacts/...`) migrates from GitHub Actions artifacts to R2 staging + `run_artifact` manifests in stages. Warm cache, patched universe, and monthly Release remain on existing paths until Phase 3/4.

## Phase 2 rollout stages

| Stage | Handoff primary | R2 role | GitHub artifact |
|-------|-----------------|---------|-----------------|
| **2a** | GitHub artifact upload/download | shadow put + shadow-validate (sha256/size) | retained |
| **2b** | R2 staging get via manifest | preferred write; primary read with GH fallback | retained as fallback |
| **2c (current)** | R2 only | primary read/write | upload/download removed |

Phase 2a contract (historical):

- Producer: GitHub artifact upload (primary) then `artifact_bus_cli.py put` (shadow)
- Consumer: GitHub artifact download (primary) then `artifact_bus_cli.py shadow-validate`
- Required artifact shadow failure, mismatch, or `validated_count=0` fails the job
- Optional artifact (`stale-exclusions-*`, `enriched-csv-*`): **local file missing** is non-fatal in shadow-validate (degraded reason in summary/JSON). If the local file exists but R2 manifest/blob is missing or mismatched, shadow-validate fails like a required artifact.

Phase 2b contract:

- **Invariant:** R2 outage alone must not block `compute_indicators`, `enrich`, or `render_and_upload`. GitHub artifact fallback success allows degraded continuation.
- Producer: GitHub artifact upload (fallback copy) then `artifact_bus_cli.py put` (preferred R2 write, `continue-on-error`). Required artifact: R2 put failure alone is non-fatal if GitHub upload succeeded; both failed fails the producer job. Optional artifact: either side missing is recorded in summary; job continues when local file is absent by contract.
- Consumer: `artifact_bus_cli.py get` (R2 primary) then conditional GitHub artifact download when `fallback_required=true`, then `record-fallback` when GitHub path used. Required artifact: both R2 get and GitHub fallback failed fails the job. Optional artifact: both missing is non-fatal with `degraded_reason` in summary/JSON.
- Observability: each handoff JSON includes `handoff_source` (`r2` / `github_fallback`), `fallback_used`, `fallback_required`, `validated_count`, `degraded_reason` where applicable. Silent fallback is forbidden.
- `shadow-validate` is not used on the consumer path in Phase 2b.
- Supabase `artifact_index` shadow commit is **deferred** to Phase 3; Phase 2 orphan = blob put ok but manifest put/validation failed

**Phase 2c promotion gate (completed):** one successful **FI-1** live run (non-replay: `run_date` empty, `is_replay=false`) with consumer `handoff_source=github_fallback` on required artifacts, plus one post-gate normal run with `handoff_source=r2`. Procedure: [phase2b_fault_injection.md](../operations/phase2b_fault_injection.md). Pre-merge gate cleared 2026-06-29 (run #179).

**Phase 2c post-merge live gate (completed):** first trading day after Phase 2c merge (PR #104) — run #180 (2026-06-30), R2-only handoff, publish success. Record: [phase2c_r2_only_cutover.md](../operations/phase2c_r2_only_cutover.md). Phase 2 daily artifact bus migration **complete**; Phase 3 next.

Phase 2c contract:

- **Invariant:** run-internal daily artifact bus uses R2 staging only. GitHub artifact upload/download and `record-fallback` are not used on the consumer or producer path.
- Producer required artifact: after local file is produced, R2 blob put or manifest put failure fails the job. No `continue-on-error`, no GitHub upload fallback, no `degraded` producer status.
- Producer optional artifact (`artifact-stale-exclusions`, `artifact-enriched-csv`): **local file missing** → `skipped_optional_missing`, job continues. Local file present but R2 put failed → job fails.
- Consumer required artifact: R2 manifest get, blob get, or sha256/size verification failure fails the job. No GitHub fallback.
- Consumer optional artifact: R2 missing → `skipped_optional_missing`, job continues. Manifest/blob mismatch → job fails (data corruption).
- Observability: successful consumer handoff JSON has `handoff_source=r2` only. `github_fallback`, `fallback_used`, and `fallback_required` must not appear in Phase 2c job summaries for successful runs.
- `r2_fault_mode` dispatch input is removed from Phase 2c workflows; R2 failure tests use Fake adapter in unit/job_integration tests.
- `record-fallback` and `shadow-validate` CLI commands remain for Phase 2a/2b rollback but are not invoked by Phase 2c workflows.
- Supabase `artifact_index` shadow commit is **deferred** to Phase 3; Phase 2 orphan = blob put ok but manifest put/validation failed

## R2 key namespaces (do not mix)

Distribution (existing, `scripts/storage/paths.py`):

- `0011_work/` — internal CSV
- `0012_paid/` — customer XLSX

Migration staging (this contract):

- `published/` — daily publish blobs + manifest (Phase 2+ publish path)
- `runs/` — per-run artifact bodies and manifests
- `cache/` — warm cache zip bodies (Phase 3)
- `monthly/` — monthly universe snapshots (Phase 4)
- `derived-snapshots/` / `derived-series/` — Phase 4.5 derived objects
- `derived-inputs/` — ADR-005 planned request manifests and seed/repair deltas（live writer なし）

**Contract:** resolve object keys from deterministic resolver (`run_id` + `run_date`) or workflow manifest outputs. Do not rely on R2 `ListObjects` in the normal consumer path.

## Phase 2 daily artifact bus

| Entry id | Legacy source name token | R2 logical key token | optional |
|----------|---------------------------|----------------------|----------|
| `artifact-daily-core-csv` | `{run_id}` | `{run_id}` | no |
| `artifact-daily-core-quality` | `{run_id}` | `{run_id}` | no |
| `artifact-daily-index-store` | `{run_id}` | `{run_id}` | no |
| `artifact-daily-ohlc-store` | `{run_id}` | `{run_id}` | no |
| `artifact-stale-exclusions` | `{run_id}` | `{run_id}` | yes |
| `artifact-daily-indicators` | `{run_date}` | `{run_id}` + `{run_date_compact}` | no |
| `artifact-enriched-csv` | `{run_date}` | `{run_id}` + `{run_date_compact}` | yes |

- Manifest kind: `run_artifact` (`docs/contracts/run_artifact_manifest_schema.md`)
- Manifest stores **logical** keys; `R2_BASE_PREFIX` is applied only in the staging adapter
- One manifest per logical artifact (`runs/daily/{run_id}/manifests/{entry_slug}.json`)
- `daily_event_cause_enrichment.yml` `enrich` is consumer of `daily-indicators-*` and producer of `enriched-csv-*`
- Reusable enrichment shares `github.run_id` with caller; keys are recomputed from `run_id` + `run_date`
- Replay: new `run_id` → new staging prefix (no active pointer collision)
- Job re-run within same run: idempotent overwrite; manifest sha256 is authoritative

## Rollback (Phase 2)

### Phase 2a (shadow period)

1. Disable R2 shadow steps via revert if R2 secrets or staging are broken; GitHub artifact remains primary
2. R2 staging objects remain until `runs/` cleanup; no ListObjects in normal path

### Phase 2b

1. Revert to Phase 2a (GitHub primary + R2 shadow) or prior commit with GitHub artifact only
2. Confirm next trading day live run before deleting rollback branch

### Phase 2c

1. Revert to Phase 2b (R2 primary + GitHub artifact fallback) commit
2. Confirm next trading day live run shows `handoff_source=r2` or `github_fallback` per Phase 2b contract
3. R2 staging objects remain until `runs/` cleanup; no ListObjects in normal path

## Scanned workflows (4)

| Workflow | Main writers |
|----------|--------------|
| `daily.yml` | daily artifacts (Phase 2c: R2 only), index/OHLC warm cache, daily Release via upload CLI |
| `daily_universe_patch.yml` | patched universe cache (sole writer) |
| `daily_event_cause_enrichment.yml` | `enriched-csv-*` (Phase 2c: R2 only; sole writer) |
| `monthly.yml` | monthly Release, debug artifacts, JPX URL cache |

## Related

- `docs/adr/adr-003-r2-supabase-control-blob-split.md`
- `docs/contracts/run_artifact_manifest_schema.md`
- `docs/contracts/daily_publish_manifest_schema.md`
- `docs/contracts/supabase_control_plane_schema.md`

## Phase 3 warm cache + control plane (current: 3c)

Machine-readable stage: phase3_rollout_stage in mapping YAML (3a | 3b | 3c).

**Stage promotion:** When changing phase3_rollout_stage in a PR, update contract test expectations and workflow steps in the same PR.

| Stage | Cache read | Cache write | GH actions/cache | Supabase commit |
|-------|------------|-------------|------------------|-----------------|
| 3a | GH primary | GH + shadow R2/Supabase | retained | shadow (non-fatal) |
| 3b | R2/Supabase primary | R2 + Supabase | fallback read | shadow (non-fatal) |
| 3c | R2/Supabase only | R2 + Supabase required | removed | required |

### Phase 3 cache entries

| Entry id | R2 | Supabase |
|----------|-----|----------|
| cache-index-store-zip-v1 | live: `cache/index-store-zip-v1/objects/sha256={object_sha256}.zip` (immutable_pointer_cas). legacy fixed `index_store.zip` only until pointer advances | cache_index + cache_pointers via CAS RPC |
| cache-ohlc-store-zip-v2 | live: `cache/ohlc-store-zip-v2/objects/sha256={object_sha256}.zip`. planned (legacy note): `cache/ohlc-store-zip-v2/objects/sha256={object_sha256}.zip` | same |
| cache-universe-patched | csv + manifest under cache/universe-patched/{monthly_tag}/{run_date}/ | cache_index patched row (no pointer) |

### patched ref filter (Option A)

`resolve_core_csv` select lists Supabase patched rows filtered by source_ref in {github.ref, refs/heads/default_branch} (GH cache equivalent).

### runs ordering

`control_plane_cli` upsert-run at end of `resolve_trading_day` (before parallel producers).

Runbook: docs/operations/phase3_warm_cache_supabase_cutover.md.

## Phase 4+ (live through ADR-005; Phase 5 remaining)

See docs/operations/issue_93_roadmap.md and docs/operations/phase4_cutover.md.

- Phase 4: monthly_snapshots, publish_status, runs lifecycle, monthly Cron, cache-jpx-url R2 migration（gate CLOSED 2026-07-22）。
- Phase 4.5: derived indicators warm cache (ADR-004; rollout 4.5c, live_gate closed via waiver 2026-08-29).
- ADR-005 (Adopted; `live_gate_005` closed 2026-09-01): Monthly new-Core backfill. Live OHLC/index cache uses `immutable_pointer_cas` (`pr-005-daily-cas` merged via PR #159). `planned_scan_workflows` empty after P4 promotion; `monthly_new_core_backfill.yml` is in live `scan_workflows`.
- Phase 5: tracks A–E（Step 5.0 トラック地図 in_progress。5.5a ping 未マージ。Auth/UI 未着手）. Gate SSOT: docs/operations/phase5_gate_status.yaml.

Live daily/monthly `upload_to_all_targets.py` TARGETS are `r2,dropbox` (optional `drive` when unfrozen). GitHub Release is **not** a live TARGET after Phase 4c. Mapping entry `release-daily-yyyymm` remains a logical published/ key; `cleanup_releases.yml` retains leftover Release assets.

## ADR-005 mapping (schema_version 6)

Top-level key `adr005`:

- `status`: `proposed` = feature_start unset; `enabled` = feature_start set in DB (YAML mirror). Does **not** mean ADR unadopted when `proposed`
- `feature_start_release_month`: YAML mirror (`null` until enable; live `2026-09` after 2026-09-01 enable). SSOT is Supabase `adr005_runtime_config` (ADR-005 §4)
- `live_cache_protocol` / `planned_cache_protocol`: `immutable_pointer_cas`
- `planned_objects`: content-addressed cache objects, seed delta, request manifest, `history_quality.json`
- `planned_writer_workflows` / `planned_scan_workflows`: do **not** copy into `scan_workflows` until the workflow files exist (P4 already promotes live `scan_workflows` when files exist)

Cache entries `cache-index-store-zip-v1` / `cache-ohlc-store-zip-v2` use live `writer_workflow: daily.yml` and live `target_r2_key_pattern: cache/{kind}/objects/sha256={object_sha256}.zip` with `retention_policy: warm_cache_immutable_pointer_cas` (`pr-005-daily-cas` merged). `writer_workflows` lists current writers. YAML `planned_*` keys are protocol aliases (not “unimplemented”); `planned_writer_workflows` includes `monthly_new_core_backfill.yml`; `planned_target_r2_key_pattern` / `planned_retention_policy` match live.

Related: `docs/adr/adr-005-monthly-new-core-backfill.md`, `docs/contracts/monthly_new_core_backfill_cloudflare_cron_dispatch.md`, `docs/contracts/monthly_new_core_backfill.md`.

