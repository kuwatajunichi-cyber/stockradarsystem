# Monthly Cloudflare Cron dispatch (Phase 4)

## Purpose

Phase 4c moves `monthly.yml` scheduled execution from GitHub `schedule` to Cloudflare Worker Cron.

## Cron

| Cron (UTC) | Workflow | Gate |
|------------|----------|------|
| `0 2 1 * *` | `monthly.yml` | `MONTHLY_DISPATCH_ENABLED=true` only after GH schedule removal |

Daily (`45 6 * * *`) and patch (`0 3 * * *`) crons are unchanged from Phase 1.

## Atomic cutover (PR-4-6b)

Same release unit:

1. `wrangler.toml` adds monthly cron (3 crons total)
2. Keep Worker env `MONTHLY_DISPATCH_ENABLED=false` (Worker cron installed but gated off)
3. `monthly.yml` sets `phase4_rollout_stage: "4c"` (Create Release removed earlier)
4. mapping `phase4_rollout_stage: "4c"`

Deploy Worker **after** merge (U-3). **Do not remove** the GitHub `schedule` in the same merge.

## Post-U-3 cutover (2026-07-14)

Steps 5-6 applied after U-3 verified three Worker crons live:

5. Removed `monthly.yml` GitHub `schedule`.
6. Set `MONTHLY_DISPATCH_ENABLED=true` and redeployed Worker.

## Related

- `workers/github-cron-dispatcher/`
- `docs/operations/phase4_cutover.md`
