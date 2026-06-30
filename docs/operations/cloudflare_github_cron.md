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

### Phase 2b (completed)

Confirmed on live runs before Phase 2c promotion:

1. Required consumer handoff summary shows `handoff_source=r2` for primary path (normal case)
2. Producer R2 puts succeeded or degraded with GitHub upload fallback copy present
3. `render_and_upload` publish completed
4. Manifest keys appear in job outputs / summary when R2 put succeeded
5. No required artifact with `handoff_failed` in summary

Optional degraded paths (`stale-exclusions`, `enriched-csv`) must be visible in summary when applicable.

### Phase 2b fault-injection check (FI-1, completed)

Controlled negative test via `workflow_dispatch` (no secret mutation). Full runbook: [phase2b_fault_injection.md](phase2b_fault_injection.md)

Checklist:

1. Inputs: `run_date` **empty**, `skip_publish=true`, `r2_fault_mode=consumer_get_prefix_miss`
2. `validate_fault_injection` passes; `is_replay=false`
3. Producer puts use prod prefix (`handoff_source=r2` on producer path); consumer gets use fault namespace → `handoff_source=github_fallback`
4. `compute_indicators`, `event_cause_enrichment`, `render_and_upload` succeed; **Upload to all targets** step skipped
5. Record Actions run URL for Phase 2c gate

Rollback during Phase 2b: revert to Phase 2a (GitHub primary + R2 shadow) or prior commit; confirm next trading day live run before deleting rollback branch.

### Phase 2c (completed)

Confirmed on live run **#180** (2026-06-30, first trading day after PR #104 merge):

1. All required producer handoffs show `r2_put_ok=true` (no `producer_degraded`)
2. All required consumer handoffs show `handoff_source=r2` (no `github_fallback`, no `fallback_used`)
3. `render_and_upload` publish completed (`Upload to all targets` success)
4. Manifest keys appear in job outputs / summary
5. No artifact with `handoff_failed` in summary

Run URL: https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28425706867

Full checklist and record: [phase2c_r2_only_cutover.md](phase2c_r2_only_cutover.md). **Phase 2c live gate closed** (Issue #93, 2026-06-30).

Rollback during Phase 2c: revert to Phase 2b commit (GitHub artifact fallback restored); confirm next trading day live run before deleting rollback branch.

## CI required

- pytest --strict-markers -m "unit or job_integration or smoke"
- npm test --prefix workers/github-cron-dispatcher

## Incident record (Phase 1 cutover)

Postmortem for the 2026-06-18/19 missed-dispatch incident, lessons learned, and checklist for later cron migration phases:

- [phase1_cron_dispatch_cutover_2026-06.md](incidents/phase1_cron_dispatch_cutover_2026-06.md)
- Issue #93 comment: https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-4756986589
