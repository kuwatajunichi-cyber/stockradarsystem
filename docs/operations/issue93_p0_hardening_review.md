# Issue #93 P0 Hardening 計画レビュー

> **注記（2026-07-22）:** 本書は **2026-07-16 時点の実装前レビュー** スナップショットです。完了判定の正本は `docs/operations/issue93_p0_hardening_status.yaml`（gate CLOSED）です。

- 判定日: 2026-07-16
- 対象: `issue93-p0-hardening_56f32c3b.plan.md`
- 照合元: Issue #93、main、GitHub Actions、Cloudflare、Supabase 本番
- 判定: **修正後に実装着手**

---

## 総括

P0 の方向性（6表 + 2 RPC の匿名遮断、`service_role` 経路維持、Phase 4 gate は触らない）は妥当です。ただし、現状のままでは P0 完了を正しく判定できません。主因は以下の3点です。

1. Security Advisor の完了条件が **8件** と誤記されている（本番は **10件**）
2. `commit_jpx_url_cache` を安全に検証する smoke 設計が未確定
3. P0 完了の機械ゲート（migration 契約テスト / honesty test）が未整備

---

## 指標

| 項目 | 値 |
|------|-----|
| RLS 無効の対象表 | 6 |
| RPC advisor findings | 4 |
| P0 対象 advisor 合計 | **10**（6 + 2 + 2） |
| 対象表の RLS policy | 0 |

---

## 重要所見

### P0: Advisor 件数が誤り

- 計画は「該当8件」を完了条件にしている
- 本番は RLS 6件 + anon RPC 2件 + authenticated RPC 2件 = **10件**
- 8件基準では2件残存しても完了扱いになる
- 修正対象: 計画 6, 15, 24, 48, 61 行

### P1: migration の正方向検査が不足

- 末尾検査は非特権の残存権限を検出する一方、`service_role` の必要権限を正に検証すると明記されていない
- 追加で検証すべき項目:
  - `service_role` が6表の必要権限を持つ
  - `service_role.rolbypassrls = true`
  - 両 RPC の `EXECUTE` が `service_role` にある
- 修正対象: 計画 30-32 行

### P1: JPX RPC smoke は本番ポインタを更新する

- `commit_jpx_url_cache` は `cache_key` を `jpx-latest-url` に固定する
- 現行 `scripts/smoke/supabase_control_plane_smoke.py` も意図的に呼んでいない（171行付近）
- 合成 smoke で安全に cleanup できない
- 証拠は以下に分ける:
  - migration / catalog で `service_role` の `EXECUTE` を確認
  - `commit_fixed_cache`: namespaced smoke
  - `commit_jpx_url_cache`: migration 後の通常 `daily_universe_patch.yml` 成功 run
- 修正対象: 計画 36, 48, 60 行

### P1: anon smoke が偽陽性になり得る

- 「全リクエストが 401 または 403」だけでは、無効キー・JWT 不備でも成功扱いになる
- 必要な検証:
  - publishable key が有効である正コントロール
  - 拒否本文はログに出さず JSON 解析
  - PostgREST エラーコード `42501` を確認
  - catalog 検査と HTTP 検査の両方を成功条件にする
- 修正対象: 計画 37 行

### P2: cleanup 失敗を検知しない

- 現行 service-role smoke は `finally` の削除例外をすべて握り潰す
- 「必ず cleanup」を受け入れ条件にするなら、漏れを smoke failure にする必要がある
- 修正対象: 計画 36-38 行

### P2: 将来の自動 grant 再発を防がない

- 現行6表・2関数だけを閉じても、`postgres` の default privileges が残れば次の public 表/RPC が再び anon/authenticated に公開される
- 本番確認済み: `public` schema の default privileges で table / function / sequence が anon/authenticated/service_role に自動 grant される状態
- 修正対象: 計画 27-32 行

### P2: P0 完了の機械ゲートがない

- roadmap 更新と監査証拠を CI で照合する契約がなく、文書だけで完了表記が先行できる
- P0 専用 status と Secrets-free honesty test が必要
- 修正対象: 計画 51-63 行

---

## 照合した現状

### Supabase 本番（`wocvepixlzqupasoipbk`）

- 状態: `ACTIVE_HEALTHY` / PostgreSQL 17.6
- 6表すべて RLS disabled
- `anon` / `authenticated` は実効 CRUD + TRUNCATE を保持
- 2 RPC は `postgres` owner / `SECURITY DEFINER` / `search_path=public`
- `anon` / `authenticated` とも両 RPC の `EXECUTE` あり
- 対象表の RLS policy: 0件
- migration history: `20260714003112 002_phase4_control_plane` の1件のみ

### Repository / GitHub

- HEAD: `eefca88`（main = origin/main）
- 最新 Test run: success
- 最新 daily / patch / monthly の記録: いずれも success
- Supabase smoke の最新成功: 2026-07-06（[run 28804476960](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/28804476960)）
- JPX RPC は smoke で明示的に未実行
- P0 migration / RLS / REVOKE は未実装（リポジトリ内に `ENABLE ROW LEVEL SECURITY` / `REVOKE` ヒットなし）
- 作業ツリーに未追跡の生成物・退避コピー（`.phase4_final/` 等）が残存

### Cloudflare 本番

- Worker: `github-cron-dispatcher`（2026-07-14 更新）
- 本番 bundle は daily / patch / monthly の3経路を含み、main と一致
- R2 bucket: `stock-radar-system` 1個
- Observability API の直近7日イベント: 0件（P0 DB 変更の阻害要因ではない）

### Issue #93 / SSOT

- Phase 4 gate: **CLOSED** 維持
- P0/P1 は post-gate hardening として追跡
- P0/P1 完了前の Phase 4.5 writer 着手は禁止
- 証拠正本: `docs/operations/issue_93_post_phase4_audit.md` と `docs/operations/issue_93_roadmap.md`
- `docs/operations/phase4_gate_status.yaml` は P0 では書き換えない

---

## 計画へ入れる修正（必須）

1. 「該当8件」を全箇所 **10件（lint ID 別に 6 + 2 + 2）** へ修正する
2. migration 末尾で `has_table_privilege` / `has_function_privilege` により、非特権の否定と `service_role` の肯定を同時検査する
3. JPX RPC は合成 smoke で呼ばず、権限カタログ + migration 後の通常 patch run を実行証拠にする
4. anon HTTP smoke に有効キーの正コントロールを追加し、拒否は status と error code `42501` を確認する
5. cleanup 失敗を smoke failure にし、smoke run 行を含む残存ゼロを検査する
6. default privileges の revoke を P0 に含めるか、少なくとも P1 の必須項目にする
7. P0 専用の status SSOT と honesty contract を追加し、証拠なしの完了表記を CI で拒否する

---

## service_role が使う操作（grant 設計チェックリスト）

P0 migration の明示 grant 対象として、少なくとも以下を含めること。

| 操作 | 表/経路 |
|------|---------|
| upsert / get / update (terminal) | `runs` |
| insert / commit / orphan / delete | `artifact_index` |
| insert / upsert / commit / orphan / list | `cache_index` |
| get / delete (cleanup/sweep) | `cache_pointers` |
| insert / commit / orphan / list tags | `monthly_snapshots` |
| insert / commit / orphan / get | `publish_status` |
| RPC | `commit_fixed_cache`, `commit_jpx_url_cache` |
| orphan sweep | `list_orphan_rows` + `delete_row`（4表） |
| patched cache | `upsert_cache_index_pending_patched` / `commit_cache_index_patched` |

---

## 参考リンク

- [Issue #93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)
- [Supabase: Securing your API](https://supabase.com/docs/guides/api/securing-your-api)
- [PostgREST error codes](https://supabase.com/docs/guides/api/rest/postgrest-error-codes)