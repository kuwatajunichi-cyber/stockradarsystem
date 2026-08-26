# Cloudflare Cron miss (2026-08-26)

`github-cron-dispatcher` Cron Triggers did not invoke the Worker on 2026-08-26. Both `daily_universe_patch.yml` (12:00 JST) and `daily.yml` (15:45 JST) never started. GitHub Actions itself was healthy (Cleanup Artifacts succeeded that day).

## Timeline (UTC)

| Time | Event |
|------|--------|
| 8/20 03:00 through 8/25 06:45 | Two successful `workersInvocationsAdaptive` rows per day (GitHub subrequest 1) |
| 8/25 06:45:49 | Last successful invocation. GHA daily https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/32818400674 |
| 8/26 03:00 | patch expected — invocation count 0 |
| 8/26 06:45 | daily expected — invocation count 0 |
| 8/26 full day | Zero Workers invocations on the account (only this dispatcher exists) |

8/26 daily was later filled as replay `run_date=2026-08-26` at 8/27 03:08 JST: https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/32998030609 . Replay does not count for Path B latest / soak.

## Direct cause

Cloudflare Cron Trigger dropped the tick (missed invocation). There is no failure row, no retry, and no platform alert.

Cloudflare documents that Cron jobs run on underutilized machines and does not retry missed fires. A similar platform incident was published for 2026-07-08. There is no matching public Cron incident for 2026-08-26. Treat this as an account-local silent skip.

## Ruled out

| Hypothesis | Evidence against |
|------|------|
| GitHub 401/403 or PAT expiry | An invocation would still appear in analytics. 8/26 has zero |
| DRY_RUN / missing env | Bindings unchanged. 8/25 still had subrequest 1 |
| Deploy wiped crons | Last deploy 2026-07-14. Three crons still registered at investigation time |
| Routing bug | Production script matches current ROUTING_TABLE |
| Green Compute | `green_compute=false` |
| Cron count limit | One Worker, three crons (Free account cap is 5) |
| CPU limit | Successful days used about 1.1-1.7ms CPU (Free Cron cap 10ms) |
| Logs missing a failure | GraphQL invocations are also empty for 8/26. Logs were `observability: null` even on success days |

`scheduled()` using `ctx.waitUntil` without await is a separate bug: it can hide post-fire dispatch failures. It did not cause 8/26 because the Worker was never invoked.

## Observability gap

- Workers Logs were disabled (`script-settings.observability = null`)
- Phase 5 Healthchecks.io is not implemented. Even then, 26h grace would miss same-day catch-up
- Nothing outside Cloudflare Cron was watching for a missing GitHub run

## Countermeasures

1. Worker: await dispatch in `scheduled()`. Enable Workers Logs in wrangler (requires deploy)
2. GitHub schedule watchdog (Cloudflare-independent): `.github/workflows/cron_dispatch_watchdog.yml` — contract `docs/contracts/cron_dispatch_watchdog.md`
3. On same-day miss, catch-up with empty inputs if Actions secret `GH_DISPATCH_TOKEN` is set. Watchdog stays red.

## Related

- `docs/operations/cloudflare_github_cron.md`
- `docs/operations/incidents/phase1_cron_dispatch_cutover_2026-06.md` (different cause: Worker not deployed)
