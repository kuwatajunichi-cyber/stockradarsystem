# Phase 3 warm cache + Supabase cutover runbook

Issue #93 Phase 3: R2 cache/ + Supabase cache_index / cache_pointers + rtifact_index.

## Rollout stage

Machine-readable: config/github_state_to_r2_supabase_mapping.yaml -> phase3_rollout_stage (3a | 3b | 3c).

**Stage promotion:** When changing phase3_rollout_stage in a PR, update contract test expectations and workflow steps in the same PR.

## Live gates

See plan Live gate section. Evidence: GitHub Actions run URL + Step Summary fields (cache_source, supabase_commit_ok).

## Orphan sweeper

scripts/storage/orphan_sweeper.py:

- R2: delete blobs for rtifact_index.status=orphan and cache_index.status=orphan
- Supabase: DELETE orphan rows older than --keep-days (default 7) after successful R2 delete
- pending orphaned rows (R2 never put) also deleted after retention

## Rollback

Revert to prior phase3_rollout_stage commit; restore ctions/cache steps if rolling back from 3c.
