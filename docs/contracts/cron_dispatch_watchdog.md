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
| `ok` | 0 | covering `workflow_dispatch` exists after expected fire minus 2 minutes, within the Tokyo day |
| `skip_closed` | 0 | XTKS closed; daily/patch not required |
| `skip_not_first` | 0 | monthly target on a Tokyo date that is not the 1st |
| `too_early` | 0 | now is before expected fire plus grace |
| `miss` | 2 | trading day (or monthly on the 1st) and no covering run. `--report-only` still exits 0 |

Coverage window: `max(Tokyo D 00:00 UTC, expected fire - 2 minutes)` to Tokyo D+1 00:00 UTC. Only `event=workflow_dispatch` counts. A leftover `schedule` run or a same-day dispatch before that window (for example morning `skip_publish`) does not cover the Cloudflare tick.

GitHub's workflow-runs API does not expose dispatch inputs. A post-fire same-day `workflow_dispatch` still covers, including `skip_publish` and replay with a past `run_date`. Empty `run_date` vs replay cannot be distinguished from the runs list.

## Catch-up

On `miss`, if repository secret `GH_DISPATCH_TOKEN` is set (same PAT as the Worker), the watchdog dispatches the target workflow on `main` with empty inputs.

Same Tokyo day plus empty `run_date` means `is_replay=false` (schedule-equivalent). Next-day manual fill with a past `run_date` is replay and does not write Path B latest.

`GITHUB_TOKEN` cannot chain `workflow_dispatch`. Catch-up requires `GH_DISPATCH_TOKEN`. Detection (red check) does not.

The watchdog job stays failed after catch-up so the Cloudflare miss remains visible.

## Non-goals

- Restoring GitHub `schedule` on `daily.yml` / `daily_universe_patch.yml` / `monthly.yml` (double-launch risk).
- Making Cloudflare Cron itself 100% reliable.
- Replacing Phase 5 Healthchecks.io (GHA success heartbeat, longer grace).
- Date-rollover misses: if the watchdog's own GitHub `schedule` is delayed past JST midnight, `resolve_trading_day` looks at D+1 and a miss on D is not recorded. Phase 5 Healthchecks.io is the longer net for that class of failure.
- Adding the MNC `*/15` Cloudflare Cron to this three-row Cloudflare-miss table (ADR-005 forbids that). MNC poller liveness is a **separate** hourly GitHub schedule (`5 * * * *` → `mnc_poller`).

## ADR-005 MNC poller liveness (`mnc_poller`)

| Watchdog cron (UTC) | Target | Miss rule |
|---------------------|--------|-----------|
| `5 * * * *` | `monthly_new_core_backfill_dispatch.yml` | While repository variable `MNC_DISPATCH_ENABLED=true`, no `workflow_dispatch` in the last 45 minutes → `miss` (exit 2). When unset/false → `ok` (`mnc_dispatch_disabled`). |

Catch-up on miss dispatches the **poller** workflow only (not `monthly_new_core_backfill.yml`).

## Related

- Incident: [docs/operations/incidents/cloudflare_cron_miss_2026-08-26.md](../operations/incidents/cloudflare_cron_miss_2026-08-26.md)
- Worker: `workers/github-cron-dispatcher/`
- Workflow: `.github/workflows/cron_dispatch_watchdog.yml`
- MNC poller contract: [monthly_new_core_backfill_cloudflare_cron_dispatch.md](monthly_new_core_backfill_cloudflare_cron_dispatch.md)
