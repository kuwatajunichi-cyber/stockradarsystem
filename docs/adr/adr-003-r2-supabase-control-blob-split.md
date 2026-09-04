# ADR-003: R2 = blob plane / Supabase = control and query-metadata plane

## Status

Accepted (Phase 0, Issue #93). Phase 4.5 境界を 2026-07-22 に明確化。

## Context

The daily/monthly pipeline depends on GitHub Actions artifacts, cache, and Releases. We migrate incrementally to Cloudflare R2 and Supabase (Issue #93).

GitHub API measurements (2026-06): artifacts ~48 MiB active, cache ~35.5 MiB, Release assets ~154 MiB; daily publish ~2.75 MiB/day. R2 free tier and optimized ops remain sufficient.

After a paid web app launch, primary cost risk shifts from GitHub Actions minutes to **download / preview / CDN cache miss**, not blob storage alone.

## Decision

### Adopt: R2 = blob plane, Supabase = control plane

| Layer | Responsibility |
|-------|----------------|
| **R2** | CSV/XLSX/zip/Parquet/JSON series/manifest bodies, cache zips, monthly snapshots, published blobs |
| **Supabase** | run state, artifact/cache index, publish status, entitlements, metric definitions、active version、small latest projection、webhook idempotency、download grants |

### Reject: all-R2 (no Supabase)

- Auth, billing, entitlements, and webhook idempotency fit a relational control plane
- Putting OHLC/cache zips (tens of MiB) in Supabase DB increases cost and complexity
- Object-store-only metadata forces ListObjects-heavy resolution

### R2 holds

- Workflow artifact bodies (`runs/...`)
- Warm cache zips (`cache/...`)
- Derived immutable daily snapshots (`derived-snapshots/...`)
- Derived Web series projections (`derived-series/...`)
- Derived inputs and supplementary rebuild deltas (`derived-inputs/...`, ADR-005 Adopted; live_gate_005 closed)
- Monthly universe CSVs (`monthly/...`)
- Daily published CSV/XLSX and publish manifests (`published/...`)
- Existing distribution prefixes `0011_work` / `0012_paid` during migration

### Supabase holds

- `runs`, `artifact_index`, `cache_index`, `monthly_snapshots`, `publish_status`
- `webhook_events`, `entitlements`, `download_grants` (entitlements detailed in Phase 5)
- Phase 4.5 の metric definition / version / active set metadata
- Free stage で active set の最新断面だけを保持する `latest_derived_observations`

### Supabase does NOT hold

- OHLC / index / patched universe zip bodies
- Daily CSV/XLSX blob bodies
- Large OHLC time-series rows
- Free stage における派生指標の全履歴 EAV / JSONB rows

### Phase 4.5 clarification: small query projection

ADR-004 の初版は「Supabase は制御面のみ」を理由に派生系列の DB 行保持を全面的に不採用とした。その後、指標をアジャイルに追加・version 化し、Phase 5 Web UI で時系列を読む要求が具体化した。

本 ADR の blob/control 分離は維持するが、**小さい再生成可能な query projection** は control metadata と同じ Supabase に保持できる。初期の Free stage では active set の最新断面だけに限定し、長期系列の本体は R2 に置く。

これにより:

- 全履歴を Supabase Free の 500 MB database に入れない。
- 指標定義、active set、認可は relational integrity を使う。
- Web 時系列 payload は R2 の無料 egress を使う。
- 有料移行後に履歴 projection を追加しても、metric ID と API contract を維持する。

詳細は [ADR-004](adr-004-derived-indicators-warm-cache.md) を参照する。

## Orphan cleanup (R2 OK, Supabase commit fails)

1. Insert `pending` row in Supabase before upload (`object_key` + idempotency key)
2. After R2 put succeeds, update `artifact_index` / `publish_status` to `committed`
3. On DB failure, record `object_key` as orphan candidate; Phase 2+ sweeper deletes or retries
4. User downloads resolve **only committed** Supabase rows (orphan R2 keys are not exposed)

## Key resolution

Normal path: resolve `object_key` from workflow outputs or Supabase metadata. See `config/github_state_to_r2_supabase_mapping.yaml`.

## Scope

- Phase 1+: upload adapters, Supabase migrations
- Phase 2+: publish manifest writes, orphan sweeper, observability
- Phase 5: users / subscriptions / payments tables
- Phase 4.5: metric registry / active set / latest projection metadata（rollout 4.5c、live_gate closed via waiver 2026-08-29）
- ADR-005: `derived-inputs/` の Monthly new-Core backfill 成果物（Adopted; live_gate_005 closed 2026-09-01）

Phase 0 is docs + contract tests only. **Production workflow behavior is unchanged.**

## Links

- Issue #93
- `config/github_state_to_r2_supabase_mapping.yaml`
- `docs/contracts/supabase_control_plane_schema.md`
- `docs/contracts/daily_publish_manifest_schema.md`
- `docs/adr/adr-004-derived-indicators-warm-cache.md`
- `docs/adr/adr-005-monthly-new-core-backfill.md`
