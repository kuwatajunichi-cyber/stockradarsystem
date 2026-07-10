# Phase 3 warm cache + Supabase cutover runbook

Issue #93 Phase 3: R2 `cache/` + Supabase `cache_index` / `cache_pointers` + `artifact_index`.

Related contract: [github_state_to_r2_supabase_mapping.md](../contracts/github_state_to_r2_supabase_mapping.md)

## Rollout stage

Machine-readable: `config/github_state_to_r2_supabase_mapping.yaml` → `phase3_rollout_stage` (`3a` | `3b` | `3c`).

Current production: **`3c`** (R2/Supabase only for warm cache; Supabase commit required).

**Stage promotion:** When changing `phase3_rollout_stage` in a PR, update contract test expectations and workflow steps in the same PR.

## Scope

**In scope (Phase 3 daily path):**

- Warm cache entries: `cache-index-store-zip-v1`, `cache-ohlc-store-zip-v2`, `cache-universe-patched`
- Supabase tables: `runs`, `artifact_index`, `cache_index`, `cache_pointers`
- CLI: `cache_bus_cli.py`, `artifact_bus_cli.py`, `control_plane_cli.py`
- Patch scheduled launch: Cloudflare Cron → Worker → `daily_universe_patch.yml` (see [daily_universe_patch_cloudflare_cron_dispatch.md](../contracts/daily_universe_patch_cloudflare_cron_dispatch.md))

**Out of scope (later phases):**

- `runs` success/failed lifecycle updates (Phase 3 upserts `running` only)
- `monthly_snapshots` / GitHub Release removal (Phase 4)
- `cache-jpx-url` on `monthly.yml` (`actions/cache` retained)
- Derived indicators warm cache (ADR-004 / Phase 4.5)

## Merge gate (CI)

Before merge:

1. `pytest --strict-markers -m "unit or job_integration or smoke"` passes (no Secrets)
2. `npm test --prefix workers/github-cron-dispatcher`
3. `reusable_quality_gate.yml` / actionlint green on PR

## Live gate status

**Phase 3c live gate: CLOSED** (2026-07-10).

Soak (3 consecutive trading days Patch + Daily success), replay verification, and orphan sweeper smoke are recorded below. Issue [#93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93) **remains OPEN** for Phase 4 / 5 — closing the issue is not required to mark this gate CLOSED.

**Issue #93 roadmap (SSOT):** [issue_93_roadmap.md](issue_93_roadmap.md)

## Post-merge live verification checklist

On trading days after Phase 3c merge (Cloudflare Cron or manual `workflow_dispatch` with `skip_publish=false` unless testing handoff only):

### Daily Universe Patch (`daily_universe_patch.yml`)

| Step | Expected |
|------|----------|
| Trigger | Cloudflare Cron `0 3 * * *` UTC → `workflow_dispatch` (before daily) |
| `put-patched` | `status: ok`, `supabase_commit_ok: true` |
| cache_key | `universe-patched-{MONTHLY_TAG}-{run_date}` for trading anchor |

### Daily Indicators (`daily.yml`)

| Job | Expected |
|-----|----------|
| `resolve_trading_day` | `upsert-run` gate summary; Supabase runs row |
| `resolve_core_csv` | Supabase patched select; `get-patched` → `cache_source: r2` when patch exists for run_date |
| `ensure_index_cache` | `get-fixed` → `cache_source: r2` (after `pip install`); `put-fixed` → `supabase_commit_ok: true` on normal run |
| `ensure_core_cache` | OHLC `get-fixed` / `put-fixed` same as index |
| Producers | `artifact_bus_cli put` → `supabase_commit_ok: true`, `artifact_index_status: committed` |
| `compute_indicators` / enrichment / render | R2 handoff `handoff_source=r2`; **Upload to all targets success** when not `skip_publish` |

**Replay run (`is_replay=true`):**

- `put-fixed` skipped (`replay_save_skipped` or equivalent); downstream R2 handoff still succeeds

**Must not appear on normal live path:**

- `ModuleNotFoundError` on `cache_bus_cli get-fixed` (deps before get-fixed)
- Silent warm cache miss swallowed without Step Summary visibility

### Soak

Record **3+ consecutive trading days** of successful scheduled Patch + Daily runs (URLs in Issue #93).

## Live verification record (CLOSED — 2026-07-10)

### Soak (3 consecutive trading days)

| run_date | Patch | Daily | Notes |
|----------|-------|-------|-------|
| 2026-07-08 | [#28914279013](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28914279013) success | [#28923227742](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28923227742) success | `get-patched` hit; `upload_status=ok`; OHLC `stale=1` (non-blocking) |
| 2026-07-09 | [#28990933691](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28990933691) success | [#28999537870](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28999537870) success | `put-patched` / warm cache / publish ok; `stale=0` |
| 2026-07-10 | [#29065886668](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29065886668) success | [#29074674287](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29074674287) success | same as 2026-07-09 |

All soak runs: Cloudflare Cron dispatch; Patch (03:00 UTC) before Daily (06:45 UTC).

**Prior evidence:** Daily [28873269318](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28873269318) (2026-07-07, warm cache hit after PR #111).

**Gate checklist (Phase 3c):**

- [x] Soak: 3 consecutive trading days Patch + Daily success
- [x] Replay run: full pipeline with index + OHLC `put-fixed` skip verified (see below)
- [x] Orphan sweeper dry-run smoke
- [ ] Deferred: delisting effective-day live gate (Issue #93 2026-06-23 handoff; not a Phase 3c blocker)

### Replay verification (2026-07-08)

| Run | run_date | Result | Notes |
|-----|----------|--------|-------|
| [#28937327595](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28937327595) | 2026-07-06 | **failure** (partial) | `is_replay=true`; index `put-fixed` → `replay_save_skipped: true` ✓; `ensure_core_cache` exit 2 — 15 delisted stale codes (6540 etc.), unrelated to replay save contract |
| [#28938449074](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28938449074) | 2026-07-07 | **success** | Full pipeline; index + OHLC `put-fixed` both `replay_save_skipped: true`; `skip_publish=true`; all jobs green |

### Orphan sweeper smoke (2026-07-08)

Post–PR #113 merge dry-run: [#28938397725](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28938397725) — **success**, `orphan_rows_processed=0`.

## Orphan sweeper

`scripts/storage/orphan_sweeper.py`:

- R2: delete blobs for `artifact_index.status=orphan` and `cache_index.status=orphan`
- Supabase: DELETE orphan rows older than `--keep-days` (default 7) after successful R2 delete

Scheduled: `.github/workflows/supabase_orphan_sweep.yml` (weekly + `workflow_dispatch`).

Manual dry-run (requires `.env` Supabase + R2):

```bash
python scripts/storage/orphan_sweeper.py --dry-run --keep-days 7
```

## Rollback

1. Revert `phase3_rollout_stage` to prior stage in mapping YAML + workflows
2. Restore `actions/cache` steps on `daily.yml` if rolling back from 3c
3. For patch: restore GitHub `schedule` on `daily_universe_patch.yml`; remove Worker cron `0 3 * * *`
4. Confirm no duplicate runs in GitHub Actions history

See [cloudflare_github_cron.md](cloudflare_github_cron.md).

## Related

- [daily_cloudflare_cron_dispatch.md](../contracts/daily_cloudflare_cron_dispatch.md)
- [daily_universe_patch_cloudflare_cron_dispatch.md](../contracts/daily_universe_patch_cloudflare_cron_dispatch.md)
- [supabase_control_plane_schema.md](../contracts/supabase_control_plane_schema.md)
- [phase1_cron_dispatch_cutover_2026-06.md](incidents/phase1_cron_dispatch_cutover_2026-06.md)
