# Cloudflare Cron dispatch watchdog

Independent GitHub Actions schedule that detects **missed Cloudflare Cron to Worker to workflow_dispatch** launches.

Cloudflare Cron Triggers do not retry a missed tick and do not alert. The 2026-08-26 incident was a silent non-invocation (no Worker analytics row, no GitHub run). Worker-side logs cannot observe a fire that never happened. Detection must live **outside** Cloudflare Cron.

## Launch paths

| Watchdog cron (UTC) | JST | Target | Expected Cloudflare fire |
|---------------------|-----|--------|--------------------------|
| `35 3 * * *` | 12:35 | `daily_universe_patch.yml` | `0 3 * * *` (12:00 JST) |
| `20 7 * * *` | 16:20 | `daily.yml` | `45 6 * * *` (15:45 JST) |
| `15 2 1 * *` | 11:15 on 1st | `monthly.yml` | `0 2 1 * *` (11:00 JST) |

Grace is 35 minutes (daily/patch) or 15 minutes (monthly). Checks before grace-end are `too_early` (exit 0).

## Verdicts

Implemented by `python -m stockradar.jobs.cron_dispatch_watchdog`.

| outcome | exit | meaning |
|---------|------|---------|
| `ok` | 0 | `workflow_dispatch` (or leftover `schedule`) exists in the Tokyo calendar-day window |
| `skip_closed` | 0 | XTKS closed; daily/patch not required |
| `too_early` | 0 | now is before expected fire plus grace |
| `miss` | 2 | trading day (or monthly) and no covering run |

Coverage window: Tokyo D 00:00 to Tokyo D+1 00:00 converted to UTC. A previous day's 15:45 JST run does not cover D.

## Catch-up

On `miss`, if repository secret `GH_DISPATCH_TOKEN` is set (same PAT as the Worker), the watchdog dispatches the target workflow on `main` with empty inputs.

Same Tokyo day plus empty `run_date` means `is_replay=false` (schedule-equivalent). Next-day manual fill with a past `run_date` is replay and does not write Path B latest.

`GITHUB_TOKEN` cannot chain `workflow_dispatch`. Catch-up requires `GH_DISPATCH_TOKEN`. Detection (red check) does not.

The watchdog job stays failed after catch-up so the Cloudflare miss remains visible.

## Non-goals

- Restoring GitHub `schedule` on `daily.yml` / `daily_universe_patch.yml` / `monthly.yml` (double-launch risk).
- Making Cloudflare Cron itself 100% reliable.
- Replacing Phase 5 Healthchecks.io (GHA success heartbeat, longer grace).

## Related

- Incident: [docs/operations/incidents/cloudflare_cron_miss_2026-08-26.md](../operations/incidents/cloudflare_cron_miss_2026-08-26.md)
- Worker: `workers/github-cron-dispatcher/`
- Workflow: `.github/workflows/cron_dispatch_watchdog.yml`
