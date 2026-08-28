# Monthly new-Core backfill Cloudflare Cron dispatch (ADR-005)

## Purpose

Start the ADR-005 outbox poller on the same Cloudflare Worker Cron path as Daily / Monthly / patch. The Monthly workflow does not chain-dispatch the worker.

**Status:** skeleton only. Worker / workflow files are unimplemented. Live `wrangler.toml` stays at 3 crons. Keep `MNC_DISPATCH_ENABLED=false` until ADR-005 section 10 step 6.

## Cron (Cloudflare Worker)

| Cron (UTC) | Workflow | Gate |
|------------|----------|------|
| `*/15 * * * *` | `monthly_new_core_backfill_dispatch.yml` | Dispatch only when Worker env `MNC_DISPATCH_ENABLED=true` |

Existing Worker crons (this contract does not change them):

| Cron (UTC) | Workflow |
|------------|----------|
| `45 6 * * *` | `daily.yml` |
| `0 3 * * *` | `daily_universe_patch.yml` |
| `0 2 1 * *` | `monthly.yml` |

After this poller is added the Worker has 4 of 5 free Cron Triggers. Re-check the limit before a fifth.

## Permissions

| Workflow | GHA permissions | Dispatch auth |
|----------|-----------------|---------------|
| `monthly_new_core_backfill_dispatch.yml` | `contents: read` only. `actions: write` forbidden | Actions secret `GH_DISPATCH_TOKEN` (same value as the Worker). **`GITHUB_TOKEN` forbidden** |
| `monthly_new_core_backfill.yml` | `contents: read` only. self-dispatch forbidden | `workflow_dispatch` from the poller only |
| `monthly.yml` | existing. do not add `actions: write` | creates outbox rows in the RPC only |

## Liveness (required)

Do **not** add a 15-minute row to the three Cloudflare-miss detectors in `docs/contracts/cron_dispatch_watchdog.md` (daily / patch / monthly).

Independent miss detection **is required** (ADR-005 section 1.3.8). It is not optional and is not deferred to a later re-review:

- GitHub `schedule` every 60 minutes (not a fourth Cloudflare Cron).
- While `MNC_DISPATCH_ENABLED=true`, miss (exit 2) if `monthly_new_core_backfill_dispatch.yml` has no `workflow_dispatch` in the last 45 minutes.
- Catch-up may dispatch the **poller** workflow only (not the worker) via `GH_DISPATCH_TOKEN`.
- Implementation PR adds this GitHub-schedule target in `cron_dispatch_watchdog.py`, distinct from the three Worker-cron miss detectors.
- Stranded `dispatch_pending` / poller job failure remain the in-band alerts **after** a tick has fired. They do not observe a Cloudflare Cron that never ran.

## Implementation PR delta

1. Add the fourth cron in `workers/github-cron-dispatcher/wrangler.toml`.
2. Register `mnc_dispatch` (name TBD) in `src/constants.js` in the same PR (unknown crons throw).
3. Merge with Worker env `MNC_DISPATCH_ENABLED=false`; set true after section 10 step 6.
4. Do not use GitHub `schedule` as the poller itself (ADR-005 rejected).
5. Add `monthly_new_core_backfill.yml` to `scan_workflows` only in the PR that adds that workflow file.

## Related

- [ADR-005](../adr/adr-005-monthly-new-core-backfill.md)
- [Monthly Cloudflare Cron](monthly_cloudflare_cron_dispatch.md)
- [Cron dispatch watchdog](cron_dispatch_watchdog.md)
- [Split runbook skeleton](monthly_new_core_backfill.md)
- `workers/github-cron-dispatcher/`
