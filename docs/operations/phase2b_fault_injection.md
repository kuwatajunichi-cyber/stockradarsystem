# Phase 2b fault injection runbook

Issue #93 Phase 2b: controlled negative test for consumer R2 get miss → GitHub artifact fallback.

Related contract: [github_state_to_r2_supabase_mapping.md](../contracts/github_state_to_r2_supabase_mapping.md)

## Phase 2c gate

Before Phase 2c promotion, complete **FI-1 once** on a **non-replay live** run:

- `workflow_dispatch` with `run_date` **empty**, `skip_publish=true`, `r2_fault_mode=consumer_get_prefix_miss`
- Job Summary: `is_replay=false`, required consumer handoffs show `handoff_source=github_fallback`
- Record the Actions run URL

FI-1P (`producer_put_invalid_cred`) is optional live; unit tests cover producer degraded.

### Live verification record (2026-06-26)

| Scenario | Run | URL | Result |
|----------|-----|-----|--------|
| **FI-1** (Phase 2c gate) | Daily Indicators **#175** | https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28243902765 | **Pass** - `is_replay=false`, required consumers `handoff_source=github_fallback`, producer puts ok, `Upload to all targets` skipped |
| **FI-1P** (optional live) | Daily Indicators **#176** | https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28244073930 | **Pass** - producer `r2_put_failed` (invalid cred by design), consumers GitHub fallback, workflow success, publish skipped |

Dispatch inputs (both): `run_date` empty, `skip_publish=true`, `head_sha=c392ed28`. Resolved `run_date=2026-06-26`, `is_open=True`.

**Post-gate:** confirm one normal scheduled/dispatch run with `handoff_source=r2` before Phase 2c promotion.

### Post-gate verification record (2026-06-29)

| Scenario | Run | URL | Result |
|----------|-----|-----|--------|
| **Post-gate normal run** | Daily Indicators **#179** | https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28353795385 | **Pass** — Cloudflare Cron dispatch, `r2_fault_mode=off`, `skip_publish=false`, all required consumers `handoff_source=r2`, publish success |

Phase 2c promotion gate **cleared** (FI-1 #175 + post-gate #179). Phase 2c implementation may proceed. See [phase2c_r2_only_cutover.md](phase2c_r2_only_cutover.md).

## Fault namespace invariant

FI-1 uses a **separate top-level R2 namespace**, not a child of `secrets.R2_BASE_PREFIX`:

| Namespace | Used by | FI-1 behavior |
|-----------|---------|---------------|
| `{R2_BASE_PREFIX}/runs/daily/...` | producer **put** (always prod prefix) | manifest/blob written (normal dual-write) |
| `fault-injection/{run_id}/...` | consumer **get** only | get miss → GitHub fallback; **no put** |

**Contract:** `fault-injection/` expressions must appear only on `artifact_bus_cli.py get` steps. Put steps must never reference fault namespace (mis-application would write isolated blobs outside prod staging).

## Scenarios

| ID | `r2_fault_mode` | Purpose | Live required |
|----|-----------------|---------|---------------|
| **FI-1** | `consumer_get_prefix_miss` | E2E consumer fallback | **Yes (Phase 2c gate)** |
| **FI-1P** | `producer_put_invalid_cred` | Producer degraded visibility | No (unit tests) |
| **FI-NEG** | — | Dual failure | Unit tests only |

Do **not** combine FI-1 and FI-1P in one run.

## Prerequisites

- Phase 2b merged; recent normal run showed `handoff_source=r2`
- Avoid overlapping Cloudflare scheduled dispatch (`concurrency: daily-indicators`)
- Trading day open (`is_open=True`) or accept job skip on closed days

## FI-1 procedure

1. GitHub Actions → **Daily Indicators** → **Run workflow**
2. Inputs:

   | Input | Value |
   |-------|-------|
   | `run_date` | **empty** |
   | `skip_publish` | **true** |
   | `r2_fault_mode` | **consumer_get_prefix_miss** |
   | `force_index` | false (default) |

3. Confirm `validate_fault_injection` job succeeds (guard rejects replay / invalid mode).
4. Verify Job Summary / logs:

   | Job | Expected |
   |-----|----------|
   | `resolve_trading_day` | `is_replay=false` |
   | `resolve_core_csv` | producer `ok`, manifest keys present, no `producer_degraded` |
   | `ensure_core_cache` | consumer: `handoff_source=github_fallback`, `fallback_used` |
   | `compute_indicators` | consumer handoffs: `github_fallback`; job success |
   | `event_cause_enrichment` | indicators get → GitHub fallback |
   | `render_and_upload` | consumer handoffs: `github_fallback`; **Upload to all targets skipped** |

5. Log grep hints: `fallback_required`, `GitHub fallback`, `handoff_source=github_fallback`, `error: manifest get failed` (non-fatal)

## FI-1P (optional live)

Separate run with `r2_fault_mode=producer_put_invalid_cred`, same guard inputs (`run_date` empty, `skip_publish=true`).

Expect producer summaries: `producer_degraded`; consumers fall back to GitHub; workflow success.

## Failure patterns

- Guard fails: typo in `r2_fault_mode`, replay (`run_date` set), or `skip_publish=false`
- No fallback: fault prefix applied to put steps (contract violation)
- `render_and_upload` skipped entirely: job `if` must keep `always()`; only publish step respects `skip_publish`

## Post-run cleanup (R2)

| Target | Action |
|--------|--------|
| `fault-injection/{run_id}/` | Empty (no put) — no cleanup |
| `runs/daily/{run_id}/` (prod staging) | Normal retention via [runs_staging_cleanup.py](../../scripts/storage/runs_staging_cleanup.py) / [cleanup_r2.yml](../../.github/workflows/cleanup_r2.yml) |
| Immediate delete (optional) | Run staging cleanup manually; publish was skipped — no customer-facing impact |

## Reusable workflow expressions

**Caller (`daily.yml`):**

```yaml
r2_fault_mode: ${{ github.event.inputs.r2_fault_mode || 'off' }}
# get step env:
R2_BASE_PREFIX: ${{ github.event.inputs.r2_fault_mode == 'consumer_get_prefix_miss' && format('fault-injection/{0}', github.run_id) || secrets.R2_BASE_PREFIX }}
```

**Callee (`daily_event_cause_enrichment.yml`):**

```yaml
# get step env:
R2_BASE_PREFIX: ${{ inputs.r2_fault_mode == 'consumer_get_prefix_miss' && format('fault-injection/{0}', github.run_id) || secrets.R2_BASE_PREFIX }}
```

## Rollback

See [cloudflare_github_cron.md](cloudflare_github_cron.md) Phase 2b rollback.
