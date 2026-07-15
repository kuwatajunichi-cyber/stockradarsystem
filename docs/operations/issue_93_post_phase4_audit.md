# Issue #93 Phase 4 後 横断監査・是正計画

**監査日:** 2026-07-15  
**対象:** リポジトリ / GitHub Actions / Cloudflare Workers・R2 / Supabase 本番  
**位置づけ:** Phase 4 gate の再判定ではなく、Phase 4.5 / 5 着手前の post-gate 品質監査

## 判定

- Phase 4 は、定義済みの merge / CI / live gate 証拠に基づき **gate CLOSED を維持**する。
- Issue #93 全体は Phase 4.5 / 5 が残るため **OPEN を維持**する。
- Supabase 制御面の匿名変更可能性は現時点の本番リスクであり、Phase 5 の Auth / entitlement 実装まで延期しない。
- Phase 4.5 の新規 cache writer を追加する前に、終端状態・冪等性・Secrets-free テストの既知欠陥を解消する。

## 監査証拠

- Repository HEAD / main CI: `3101247`, Actions run `29423559036`
- Daily 4c live: `29395132842`
- Monthly dispatch/build live: `29341370858`
- Cloudflare: 本番 Worker bundle が tracked main の3経路と一致、R2 bucket `stock-radar-system`
- Supabase: project `ACTIVE_HEALTHY`、`monthly_snapshots` 2件 committed、`publish_status` 8件 committed
- ローカル再検証: CI対象 pytest 237 passed、Worker tests 28 passed

## 是正トラックと最適タイミング

### P0: 即時セキュリティ hardening（Phase 4.5 より前）

対象:

1. `public` の制御面6表（`runs`, `artifact_index`, `cache_index`, `cache_pointers`, `monthly_snapshots`, `publish_status`）で RLS が無効。
2. `commit_fixed_cache` / `commit_jpx_url_cache` が `PUBLIC`, `anon`, `authenticated` から実行可能。

本番では `anon` / `authenticated` に SELECT / INSERT / UPDATE / DELETE / TRUNCATE を含む権限がある。これは将来機能ではなく現在の防御欠陥である。

是正方針:

- RLS を有効化し、Phase 5 の利用者向け policy 完成までは匿名・一般認証利用者に書込み policy を付与しない。
- table privilege と `SECURITY DEFINER` RPC の EXECUTE を `service_role` に限定する。
- GHA の service role 経路が継続動作することを smoke で確認する。
- Auth / entitlement に基づく細粒度 policy は Phase 5 に残す。

### P1: Phase 4 post-gate reliability hardening（Phase 4.5 着手ゲート）

対象:

1. daily finalizer が enrichment の `failure` / `cancelled` を `skipped` に正規化し、`runs.status=success` にし得る。
2. terminal decision が `failed` でも、Supabase update が成功すれば GHA workflow 自体が success になり得る。
3. `runs` 48行中36行が `running` のまま残り、監査集計を汚染する。
4. committed `publish_status` と異なる blob を同一論理キーで再実行した場合の fail-fast 契約が弱い。

是正方針:

- enrichment の `failure` / `cancelled` は terminal resolver へそのまま渡す。
- terminal `failed` は GHA workflow の結論にも反映する。
- stale `running` の backfill と timeout reconciliation を追加する。
- committed 行との hash / object key 不一致は通常再実行で fail-fast とし、reconcile 操作と分離する。

Phase 4.5 着手ゲートへ、terminal semantics 修正、stale row backfill、publish mismatch 契約固定を追加する。

### P2: Phase 4.5 と同時に行う品質基盤強化

- `monthly_bus_cli` / `publish_bus_cli` の Fake ベース Secrets-free unit test
- `daily.yml` の publish / finalize 配線を固定する job_integration 契約テスト
- `FakeSupabaseControlAdapter` と Protocol に混入した具象 REST 実装の整理
- `src/stockradar/storage` の段階的 mypy 対象化
- 本番 migration history に `001_phase3_control_plane` がない状態の baseline / drift 確認

Phase 4.5 は `commit_fixed_cache` を再利用するため、既存 bus の Fake / 冪等性テストを同時に強化する。

### P3: Phase 5 に維持する工程

- Supabase Auth / entitlement / webhook と利用者別 RLS policy
- 署名付き download API
- Healthchecks.io heartbeat と Supabase 集計ビュー
- Distribution cutover

P0 は「未認証主体を遮断する防御」、P3 は「認証済み利用者へ何を許可するか」であり、分離して実施する。

## 運用チェックポイント

- 2026-08-01 02:00 UTC の monthly Cloudflare Cron 自然発火を初回定時証拠として記録する。
- Workers observability で監査期間中イベントを取得できなかったため、dispatch failure の観測経路を P1 で確認する。

## リポジトリ衛生

`.phase4_final/`, `_write_gate_ssot.py`, `.tmp_*`, `.wrangler/` は tracked 正本ではないが、古い gate SSOT / DDL / workflow コピーを含む。次工程着手前に削除または明示的に ignore / archive する。

## Phase 4 gate との関係

本監査所見は Phase 4 live gate 証拠を否定しないため、`phase4_gate_status.yaml` の `overall_status: closed` は変更しない。是正は Phase 4 post-gate hardening として追跡し、P0 / P1 未完了のまま Phase 4.5 の新規 writer 実装へ進まない。
