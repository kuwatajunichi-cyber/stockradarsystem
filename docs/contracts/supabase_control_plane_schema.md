# Supabase control plane schema (Phase 3 + Phase 4, Phase 4.5 planned boundary)

## Purpose

Control plane tables reference R2 blob keys. **No blob bodies in Supabase** (ADR-003).

DDL source of truth:

- Phase 3: `supabase/migrations/001_phase3_control_plane.sql`
- Phase 4: `supabase/migrations/002_phase4_control_plane.sql`

Phase 4.5 の metric registry / latest projection は設計済み・未実装であり、現時点の DDL 正本には含まれない。契約は `docs/adr/adr-004-derived-indicators-warm-cache.md` を参照する。

## Tables

| Table | Phase | Role |
|-------|-------|------|
| runs | 3 | Workflow execution anchor (`upsert-run` + `update-run` terminal) |
| artifact_index | 3 | Run artifact -> R2 object_key |
| cache_index | 3 | Warm cache history (fixed + patched) |
| cache_pointers | 3 | Active fixed-cache pointer |
| monthly_snapshots | 4 | Monthly universe snapshot metadata + object_keys JSONB |
| publish_status | 4 | Daily publish committed rows (DB is source of truth) |

## Phase 4.5 planned tables（未実装 → DDL: 004/005）

| Logical table | Role | Free-stage retention |
|---------------|------|----------------------|
| metric_definitions | Stable metric identity / type / lifecycle | Definitions are retained |
| metric_versions | Immutable formula / parameters / missing policy | Versions are retained |
| metric_set_versions | Ordered version set / draft-shadow-active-retired | Sets are retained; REST insert draft-only (trigger); lifecycle via RPC |
| metric_set_members | FK-ordered junction (set ↔ metric version) | Members are retained |
| active_metric_set | Single active pointer updated by CAS | One active pointer; service_role SELECT only (mutations via `activate_metric_set_cas`) |
| derived_object_index | Committed R2 snapshot / series metadata | Audit and active objects; snapshots immutable (one committed per object_key), series regeneratable (pending per object_key, prior committed orphaned on commit); REST insert pending-only, commit via RPC |
| latest_derived_observations | Latest values per instrument and active set | Latest row only |

Phase 4.5 RPC (service_role only): `commit_derived_object`, `transition_metric_set`, `activate_metric_set_cas`.

DDL source of truth:

- Phase 4.5: `supabase/migrations/004_phase45_metric_registry.sql`
- Hardening: `supabase/migrations/005_phase45_metric_registry_hardening.sql`

Phase 4.5 Free stage では全履歴 `derived_observations` を作らない。長期系列は R2 `derived-snapshots/...` / `derived-series/...` に保持し、Supabase database 350 MB warning、400 MB cleanup を契約境界とする。

初期 RLS / privilege:

- write / commit / active CAS は `service_role` のみ。
- `anon` / `authenticated` への直接 table write policy は付与しない。
- Phase 5 API は entitlement 確認後に必要な R2 series を返し、R2 bucket を直接 public にしない。

## runs (Phase 4 terminal)

- Start: `upsert-run --status running` (always, including market closed days)
- End: `update-run --status success|failed` via `finalize_run` job
- `degraded_reason=market_closed` when `is_open=False`
- Terminal `failed` must propagate to GHA workflow conclusion `failure` (P1: `finalize_run` exits 1 after successful `update-run`)

## monthly_snapshots

- UNIQUE (`monthly_tag`)
- Table `sha256` must equal `object_keys.core.sha256` (DB CHECK)
- Write path: `monthly_bus_cli commit-snapshot` only (pending -> R2 put x4 -> committed)

## publish_status

- UNIQUE (`run_id`, `logical_kind`) — max 2 rows per daily run
- Write path: `publish_bus_cli commit` only
- R2 manifest is derivative; reconcile via `publish_bus_cli reconcile-manifest`
- **Committed mismatch fail-fast (P1):** if an existing `committed` row disagrees on `sha256`, `size_bytes`, or `object_key`, `commit` returns **exit 2** without R2 put or Supabase mutation. Stage-independent (not gated by `publish_commit_is_fatal`).

## RPC: commit_jpx_url_cache

Fixed cache key `jpx-latest-url`, object key `cache/jpx-url/jpx_latest_url.txt`.

Write path: pending insert -> R2 put -> RPC with `p_history_id` (never NULL on commit path).

## mapping invariants (Phase 4)

```yaml
schema_version: 5
phase3_rollout_stage: "3c"   # must not regress to 3a
phase4_rollout_stage: "4a"|"4b"|"4c"
phase4_5_rollout_stage: "off"|"4.5a"|"4.5b"|"4.5c"
```

## Related

- docs/adr/adr-003-r2-supabase-control-blob-split.md
- config/github_state_to_r2_supabase_mapping.yaml
- docs/contracts/daily_publish_manifest_schema.md
- docs/adr/adr-004-derived-indicators-warm-cache.md
