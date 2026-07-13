# Supabase control plane schema (Phase 3 + Phase 4)

## Purpose

Control plane tables reference R2 blob keys. **No blob bodies in Supabase** (ADR-003).

DDL source of truth:

- Phase 3: `supabase/migrations/001_phase3_control_plane.sql`
- Phase 4: `supabase/migrations/002_phase4_control_plane.sql`

## Tables

| Table | Phase | Role |
|-------|-------|------|
| runs | 3 | Workflow execution anchor (`upsert-run` + `update-run` terminal) |
| artifact_index | 3 | Run artifact -> R2 object_key |
| cache_index | 3 | Warm cache history (fixed + patched) |
| cache_pointers | 3 | Active fixed-cache pointer |
| monthly_snapshots | 4 | Monthly universe snapshot metadata + object_keys JSONB |
| publish_status | 4 | Daily publish committed rows (DB is source of truth) |

## runs (Phase 4 terminal)

- Start: `upsert-run --status running` (always, including market closed days)
- End: `update-run --status success|failed` via `finalize_run` job
- `degraded_reason=market_closed` when `is_open=False`

## monthly_snapshots

- UNIQUE (`monthly_tag`)
- Table `sha256` must equal `object_keys.core.sha256` (DB CHECK)
- Write path: `monthly_bus_cli commit-snapshot` only (pending -> R2 put x4 -> committed)

## publish_status

- UNIQUE (`run_id`, `logical_kind`) — max 2 rows per daily run
- Write path: `publish_bus_cli commit` only
- R2 manifest is derivative; reconcile via `publish_bus_cli reconcile-manifest`

## RPC: commit_jpx_url_cache

Fixed cache key `jpx-latest-url`, object key `cache/jpx-url/jpx_latest_url.txt`.

Write path: pending insert -> R2 put -> RPC with `p_history_id` (never NULL on commit path).

## mapping invariants (Phase 4)

```yaml
schema_version: 4
phase3_rollout_stage: "3c"   # must not regress to 3a
phase4_rollout_stage: "4a"|"4b"|"4c"
```

## Related

- docs/adr/adr-003-r2-supabase-control-blob-split.md
- config/github_state_to_r2_supabase_mapping.yaml
- docs/contracts/daily_publish_manifest_schema.md
