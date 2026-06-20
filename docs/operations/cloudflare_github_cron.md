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

## Phase 2 live run gate (after merge)

Before promoting Phase 2b (R2 primary), confirm on the next trading day live `daily.yml` run:

1. All required producer shadow puts succeeded (`resolve_core_csv`, `ensure_index_cache`, `ensure_core_cache`, `compute_indicators`, enrichment)
2. Consumer shadow validation summary shows `validated_count > 0` for required artifacts
3. No required shadow mismatch; optional skips (`stale-exclusions`, `enriched-csv`) are visible in summary when applicable
4. `render_and_upload` published from GitHub artifact primary path
5. Manifest keys appear in job outputs / summary (`core_csv_manifest_key`, `daily_indicators_manifest_key`, `enriched_manifest_key`, etc.)

Rollback during Phase 2a: revert R2 shadow steps only; GitHub artifact handoff continues unchanged.

## CI required

- pytest --strict-markers -m "unit or job_integration or smoke"
- npm test --prefix workers/github-cron-dispatcher

## Incident record (Phase 1 cutover)

Postmortem for the 2026-06-18/19 missed-dispatch incident, lessons learned, and checklist for later cron migration phases:

- [phase1_cron_dispatch_cutover_2026-06.md](incidents/phase1_cron_dispatch_cutover_2026-06.md)
- Issue #93 comment: https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-4756986589
