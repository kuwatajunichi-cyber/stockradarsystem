# daily.yml Cloudflare Cron dispatch contract (Phase 1)

Issue #93 Phase 1: daily.yml scheduled runs move from GitHub Actions schedule
to Cloudflare Cron Trigger -> Worker -> GitHub workflow_dispatch.

## Launch paths

| Path | Canonical (Phase 1+) | Notes |
|------|----------------------|-------|
| Scheduled (weekdays) | Cloudflare Cron 37 6 * * MON-FRI (UTC) -> Worker -> workflow_dispatch | JST 15:37 Mon-Fri |
| Manual replay / debug | GitHub UI / gh workflow run workflow_dispatch | unchanged |
| GitHub schedule | disabled (removed) | prevents double launch |

## daily.yml retained contract

- workflow_dispatch inputs (unchanged): run_date (default empty), skip_publish, force_index
- concurrency: group daily-indicators, cancel-in-progress false
- artifact/cache/publish jobs: unchanged in Phase 1

## schedule -> workflow_dispatch equivalence

Worker normal dispatch does NOT pass run_date (empty inputs).
validate_daily_dispatch_run_date.validate_input("") returns (False, None) -> is_replay=false,
equivalent to former schedule launch.

Ref: src/stockradar/jobs/validate_daily_dispatch_run_date.py

## Cron constant

DAILY_CRON = "37 6 * * MON-FRI"

Verified in:
- workers/github-cron-dispatcher/wrangler.toml triggers.crons
- workers/github-cron-dispatcher/src/constants.js DAILY_CRON
- pytest and Worker npm test

Former GitHub schedule baseline: 37 6 * * 1-5 (semantically MON-FRI).

## Other workflows

Phase 1 leaves daily_universe_patch.yml / monthly.yml / cleanup schedules unchanged.

## Rollback

1. Disable Cloudflare Worker Cron Trigger.
2. Restore daily.yml schedule: cron "37 6 * * 1-5".
3. Confirm no double runs in GitHub Actions history.

## Related

- Worker I/O: docs/operations/cloudflare_github_cron.md
- Replay: docs/contracts/daily_replay_and_monthly_universe.md
