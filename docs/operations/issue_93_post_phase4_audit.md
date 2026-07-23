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

Phase 4.5 初版は `commit_fixed_cache` 再利用を想定したが、2026-07-22 の ADR-004 改訂で派生 snapshot は immutable key + logical digest を採用した。既存 bus の Fake / 冪等性テスト強化は P2 として継続するが、派生 snapshot の active commit に固定 key の last-write-wins を再利用しない。

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

本監査所見は Phase 4 live gate 証拠を否定しない。2026-07-22 ゲート監査で PR-4-2 merge CI 失敗を SSOT に正直記録し、corrective evidence で再検証済み。是正は Phase 4 post-gate hardening として追跡し、P0 gate CLOSED（2026-07-16）。P1 gate CLOSED（2026-07-17）。Phase 4.5 は契約・PoC・pure logic に着手可能。本番 writer / active cutover は Phase 4.5 preflight 完了まで未承認。

## Phase 4.5 設計再評価（2026-07-22）

利用者が内部・少数の間はインフラ固定費を避け、利用者増加時に拡張する前提で ADR-004 を改訂した。

主要変更:

- 全期間単一 zip の固定 key 上書きを廃止。
- R2 immutable daily Parquet を監査・再構築の正本とする。
- Web UI 用に R2 銘柄×年 JSON gzip projection を持つ。
- Supabase Free は metric registry、active set、R2 metadata、最新断面だけを保持する。
- 指標追加・削除・式変更を immutable metric version / metric set で管理する。
- active set は CAS、通常 mismatch は fail-fast、訂正は reconcile に分離する。

再評価:

- **推進判定:** 条件付き GO。
- **許可範囲:** 契約、容量・backfill PoC、pure logic、Fake I/O、shadow。
- **未承認:** 本番 shared writer、active cutover、Phase 4.5 CLOSED 報告。
- **主要 blocker:** Layer 1 5 年保持、Free budget 実測、DDL/RLS/CAS、専用 gate SSOT、現行 `put-fixed` defect。

リスク再評価:

| リスク | 重大度 / 可能性 | 対策 / gate |
|--------|-----------------|-------------|
| 現行 730 暦日の Layer 1 では長期グラフ + RS252 の backfill に不足 | High / High | `graph window + lookback + buffer` で5年保持を PoC。取得元ポリシー、容量、時間を検証 |
| 3,000 銘柄の当年 series 更新による R2 request / workflow 時間増 | Medium / Medium | bounded parallelism と shard 実測。月80万 Class A または job SLO 超過で設計見直し |
| Supabase Free 500 MB と既存 control/Auth growth の競合 | High / Medium | latest only、350 MB warning、400 MB cleanup、全履歴 DB projection 禁止 |
| metric version 増加による R2 容量・意味の混乱 | Medium / High | definition fingerprint、draft/shadow/active/retired、retired retention |
| 日次 CSV と Web 系列の同日値不一致 | High / Medium | 同一 pure 関数、cross-artifact contract test、logical digest |
| normal / replay / backfill / reconcile 混同による過去値書換え | High / Medium | entrypoint 分離、expected old digest、監査ログ |
| Free plan の pause・性能・復旧制約 | Medium（内部）/ High（外部） | 内部・βに限定し、外部 SLO 導入前に Pro 移行 |
| R2 series の無認可公開 | High / Medium | private bucket、Phase 5 API で entitlement 確認後に配信 |

詳細仕様は [ADR-004](../adr/adr-004-derived-indicators-warm-cache.md)、進捗判定は [Issue #93 roadmap](issue_93_roadmap.md) を正本とする。

## P0 hardening progress (2026-07-16)

- Migration: `supabase/migrations/003_p0_control_plane_hardening.sql`
- Production apply: 2026-07-15 UTC (full DDL via execute_sql; migration history records `003_p0_control_plane_hardening`)
- RLS enabled on all six control-plane tables; no anon/authenticated policies
- Table ACL and RPC EXECUTE limited to `service_role`
- Security advisor P0 findings: 10 -> 0 (residual INFO: `rls_enabled_no_policy` on six tables, expected for P0)
- Local verification: pytest CI subset 254 passed; service-role smoke passed; anon security smoke passed
- GHA live smokes: service-role [29437920623](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29437920623); anon security [29438553157](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29438553157)
- Post-merge live gates (2026-07-15): patch [29439142426](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29439142426) success; monthly [29439147108](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29439147108) success (`commit_jpx_url_cache` via put-jpx-url); daily replay [29448723855](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29448723855) success (`run_date=2026-07-15`, `force_index=true`)
- Initial daily dispatches [29439144924](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29439144924) / [29444244349](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29444244349) failed on `ensure_index_cache` stale (operational; replay satisfies gate)
- SSOT: `docs/operations/issue93_p0_hardening_status.yaml` (`closed`)

## P1 hardening progress (2026-07-17)

- PR stack: #127–#131 merged to main (final merge `f19f587`)
- Terminal semantics: enrichment failure/cancelled no longer masked as skipped
- GHA conclusion sync: terminal `failed` propagates to workflow exit code
- Stale `running` reconcile: 35 → 0 rows ([run 29565078632](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29565078632))
- Publish mismatch fail-fast: committed hash mismatch exits 2 without R2 put
- Latest scheduled daily success: [run 29897774884](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/29897774884) (2026-07-22)
- SSOT: `docs/operations/issue93_p1_hardening_status.yaml` (`closed`)