# Issue #93 P1 — Dispatch failure observability runbook

**Purpose:** Document how to observe Cloudflare cron dispatch failures and escalate when Worker logs are unavailable.

## 1. Cloudflare Workers Observability (github-cron-dispatcher)

1. Open Cloudflare dashboard → Workers & Pages → `github-cron-dispatcher`.
2. Observability → Logs. Filter last **7 days**.
3. Search for `dispatch failed`, non-2xx GitHub API responses, or missing `workflow_dispatch` success.
4. Record: timestamp (UTC), cron route (`daily` / `monthly` / `patch`), HTTP status, error body snippet.

## 1b. Silent Cron miss (no Worker invocation)

Workers Logs cannot show a fire that never happened. Use GraphQL `workersInvocationsAdaptive` and GitHub Actions runs for the expected UTC minute. Same-day detector: `.github/workflows/cron_dispatch_watchdog.yml`.

If both patch and daily are missing the same calendar day, treat as Cloudflare Cron skip (see [cloudflare_cron_miss_2026-08-26.md](incidents/cloudflare_cron_miss_2026-08-26.md)), not a GitHub outage.

## 2. Dispatch failure — alternative evidence

When Worker logs are empty or delayed:

1. GitHub Actions → filter workflows: `daily.yml`, `monthly.yml`, `daily_universe_patch.yml`.
2. Confirm expected schedule window had a run; if not, use **workflow_dispatch** manually:
   - Daily: `.github/workflows/daily.yml` → Run workflow (set `run_date`, `force_index=true` if index stale).
   - Patch: `.github/workflows/daily_universe_patch.yml`.
   - Monthly: `.github/workflows/monthly.yml`.
3. Save the manual dispatch run URL as operational evidence.

## 3. Escalation

| Symptom | Action |
|---------|--------|
| Cron silent, **no** Worker invocation | Watchdog red check; same-day empty `workflow_dispatch` catch-up; inspect GraphQL invocations |
| Cron silent, Worker 5xx | Check Cloudflare status; re-deploy worker; manual dispatch |
| GitHub 401/403 on dispatch | Rotate `GH_DISPATCH_TOKEN` via `wrangler secret put GH_DISPATCH_TOKEN`; verify `GITHUB_OWNER` / `GITHUB_REPO` / `GITHUB_REF` |
| Supabase upsert-run fails | Check P0 RLS/privilege; run service-role smoke |

## 4. 2026-08-01 monthly Cron checkpoint (audit template)

Record after natural August monthly fire:

| Field | Value |
|-------|-------|
| Expected cron (UTC) | _fill_ |
| Worker log URL / snippet | _fill_ |
| GHA monthly run URL | _fill_ |
| runs.status terminal | success / failed |
| monthly_snapshots committed | yes / no |

## Related

- [issue93_p1_hardening_status.yaml](issue93_p1_hardening_status.yaml)
- [issue_93_post_phase4_audit.md](issue_93_post_phase4_audit.md)
- Worker: `workers/github-cron-dispatcher/`