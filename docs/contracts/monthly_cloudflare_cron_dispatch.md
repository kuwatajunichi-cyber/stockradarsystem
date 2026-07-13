# Monthly Cloudflare Cron dispatch (Phase 4)

## Purpose

Phase 4c moves `monthly.yml` scheduled execution from GitHub `schedule` to Cloudflare Worker Cron.

## Cron

| Cron (UTC) | Workflow | Gate |
|------------|----------|------|
| `0 2 1 * *` | `monthly.yml` | `MONTHLY_DISPATCH_ENABLED=true` in Worker env |

Daily (`45 6 * * *`) and patch (`0 3 * * *`) crons are unchanged from Phase 1.

## Atomic cutover (PR-4-6b)

Same release unit:

1. `wrangler.toml` adds monthly cron (3 crons total)
2. Worker env `MONTHLY_DISPATCH_ENABLED=true`
3. `monthly.yml` removes GitHub `schedule` and Create Release
4. mapping `phase4_rollout_stage: "4c"`

Deploy Worker **after** merge (U-3). Do not remove GH schedule before Worker deploy is live.

## Related

- `workers/github-cron-dispatcher/`
- `docs/operations/phase4_cutover.md`
