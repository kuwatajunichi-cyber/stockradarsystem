# Cloudflare Cron -> GitHub workflow_dispatch operations

Issue #93 Phase 1: daily.yml scheduled launch via Cloudflare Worker workflow_dispatch.

## Architecture

Cloudflare Cron (45 6 * * * UTC)
  -> workers/github-cron-dispatcher (scheduled handler)
  -> POST /repos/{owner}/{repo}/actions/workflows/daily.yml/dispatches
  -> .github/workflows/daily.yml (GitHub Actions compute runner)

- JST: daily 15:45 (UTC 06:45)
- Constant: DAILY_CRON = "45 6 * * *"

Contract: docs/contracts/daily_cloudflare_cron_dispatch.md

## Worker layout

workers/github-cron-dispatcher/
  src/index.js, src/constants.js, src/dispatch.js
  wrangler.toml, package.json

## Secrets / Vars

Secret (required): GH_DISPATCH_TOKEN (do NOT use GITHUB_TOKEN name)

  cd workers/github-cron-dispatcher
  wrangler secret put GH_DISPATCH_TOKEN

Minimum scope: fine-grained PAT or GitHub App token with Actions read/write on target repo.

Vars (required): GITHUB_OWNER, GITHUB_REPO, GITHUB_REF (default main)

Optional: DISPATCH_SKIP_PUBLISH, DISPATCH_FORCE_INDEX, DRY_RUN

## Routing (Phase 1)

| Cron | Workflow | inputs |
|------|----------|--------|
| 45 6 * * * | daily.yml | none (no run_date) |

## Logging

JSON one-line logs (source: github-cron-dispatcher). Never log token values.

## Deploy (manual)

  cd workers/github-cron-dispatcher
  npm test
  wrangler deploy

## Manual smoke (not CI required)

  npm test --prefix workers/github-cron-dispatcher
  python scripts/smoke/phase1_cloudflare_dispatch_smoke.py
  LIVE_DISPATCH_ENABLED=true python scripts/smoke/phase1_cloudflare_dispatch_smoke.py --live-dispatch

Requires gh auth token or GH_DISPATCH_TOKEN in .env.
Cloudflare verification needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.

## Rollback

1. Disable Cloudflare Cron
2. Restore daily.yml schedule cron "37 6 * * 1-5"
3. Confirm no duplicate runs

## Phase 2 live run gate

### Phase 2a (completed)

Confirmed on live run before Phase 2b promotion:

1. All required producer shadow puts succeeded
2. Consumer shadow validation summary showed `validated_count > 0` for required artifacts
3. `render_and_upload` published successfully

### Phase 2b (current)

After Phase 2b merge, confirm on the next trading day live `daily.yml` run:

1. Required consumer handoff summary shows `handoff_source=r2` for primary path (normal case)
2. Producer R2 puts succeeded or degraded with GitHub upload fallback copy present
3. `render_and_upload` publish completed
4. Manifest keys appear in job outputs / summary when R2 put succeeded
5. No required artifact with `handoff_failed` in summary

Optional degraded paths (`stale-exclusions`, `enriched-csv`) must be visible in summary when applicable.

### Phase 2b fault-injection check (once after merge)

Run one controlled negative test without breaking production secrets:

1. Temporarily override R2 env in a manual `workflow_dispatch` (invalid `R2_ACCESS_KEY_ID` or empty `R2_BASE_PREFIX`) **or** use a dedicated test job/workflow that simulates R2 get failure
2. Confirm required consumers fall back to GitHub artifact download
3. Confirm `compute_indicators`, `enrich`, and `render_and_upload` complete with `handoff_source=github_fallback` in summary
4. Restore normal R2 env before the next scheduled run

Rollback during Phase 2b: revert to Phase 2a (GitHub primary + R2 shadow) or prior commit; confirm next trading day live run before deleting rollback branch.

## CI required

- pytest --strict-markers -m "unit or job_integration or smoke"
- npm test --prefix workers/github-cron-dispatcher

## Incident record (Phase 1 cutover)

Postmortem for the 2026-06-18/19 missed-dispatch incident, lessons learned, and checklist for later cron migration phases:

- [phase1_cron_dispatch_cutover_2026-06.md](incidents/phase1_cron_dispatch_cutover_2026-06.md)
- Issue #93 comment: https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-4756986589
