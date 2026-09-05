# Issue #93 ロードマップ（正本）

GitHub Issue: [#93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)

**改訂日:** 2026-09-04
**SSOT:** 詳細正本。Issue #93 本文は要約 + リンク。

設計根拠: [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md)、[ADR-004](../adr/adr-004-derived-indicators-warm-cache.md)。隣接 Adopted（live_gate closed）: [ADR-005](../adr/adr-005-monthly-new-core-backfill.md)

## フェーズ状態

| Phase | テーマ | 状態 |
|-------|--------|------|
| 0-2c | 契約 / Cron / R2 artifact bus | 完了 |
| 3c | warm cache + Supabase | **gate CLOSED** (2026-07-10) |
| 4 | 月次 + publish + runs + Cron | **gate CLOSED** (2026-07-22) |
| 4.5 | 派生指標時系列基盤 | **PR-45-1..4 merged・rollout 4.5c・Path B active・live_gate closed (user-authorized waiver 2026-08-29)・capacity_gate closed** |
| 5 | entitlements + observability | **in_progress（トラック地図。5.5a ping 未マージ。Auth/UI 未着手）** |

Phase 3c gate CLOSED（runbook 記録済）。Issue #93 は Phase 5 が残るため **OPEN** 維持。Phase 4.5 gate は CLOSED（soak は waiver。連続 3 営業日達成とは書かない）。ADR-005 `live_gate_005` は CLOSED（2026-09-01）。

## Phase 4 後監査と是正順序（2026-07-15）

詳細: [issue_93_post_phase4_audit.md](issue_93_post_phase4_audit.md)

| 優先度 | タイミング | 内容 |
|--------|------------|------|
| **P0** | **即時・Phase 4.5 前** | **gate CLOSED** (2026-07-16): Supabase 6表の RLS / table privilege、`SECURITY DEFINER` RPC の匿名実行権限を hardening |
| **P1** | **Phase 4.5 着手ゲート** |**gate CLOSED** (2026-07-17): terminal semantics、GHA/Supabase 結論一致、stale `running`、publish mismatch fail-fast|
| **P2** | Phase 4.5 と同時 | bus CLI Fake test、daily publish/finalize 契約、storage mypy、migration baseline（**形式ゲートなし・残債。Phase 5 着手ブロッカーではない**） |
| **P3** | Phase 5 | Auth/entitlement に基づく細粒度 RLS、API、heartbeat、distribution |

P0 は現在の匿名変更可能性を遮断する防御であり、Phase 5 の利用者別認可とは分離する。P0 gate CLOSED（2026-07-16）。P1 gate CLOSED（2026-07-17）。preflight 5/5 closed。rollout 4.5c。Path B 13209d23 は 2026-08-22 に CAS で active。placeholder 11111111 は retired。live_gate_45c は 2026-08-29 の user-authorized waiver で closed（連続 soak 達成とは書かない。8/26 Cron miss）。capacity_gate は Path B v2 safety 1.20 で closed。Phase 4.5 gate CLOSED。

## Phase 4（2026-07-08 決定: 単体フェーズ）

In: monthly_snapshots, daily/patch 月次解決切替, publish_status, runs lifecycle, monthly Cron, cache-jpx-url。  
Out: 派生 cache(4.5), auth(5), published/統一(5), cleanup Cron(5+)。  
詳細: [phase4_cutover.md](phase4_cutover.md)  
ゲート証拠: [phase4_gate_status.yaml](phase4_gate_status.yaml)

## Phase 4.5（派生指標時系列基盤）

詳細:

- 設計判断: [ADR-004](../adr/adr-004-derived-indicators-warm-cache.md)
- 推進判定・リスク: 本節および [Phase 4 post-audit](issue_93_post_phase4_audit.md)

採用方針:

- R2 に immutable daily Parquet と銘柄×年 JSON gzip を保持する。
- Supabase Free には metric definition / version / active set / object metadata / 最新断面だけを保持する。
- 指標追加・変更・削除は immutable metric version と metric set lifecycle で扱う。
- 無料段階は内部・少数利用に限定し、容量・MAU・SLO gate で有料構成へ移行する。
- normal / replay / backfill / reconcile を分離し、active 切替は CAS とする。

現時点の preflight blocker（**5/5 closed**, PR #134 + #135）:

1. ~~Layer 1 5年保持・backfill 実現性~~ → closed（PoC eligible + layer1_r2 見積）
2. ~~put-fixed 誤 cache key~~ → closed
3. ~~metric registry DDL 契約~~ → closed（本番 004/005 apply 2026-08-12）
4. ~~Supabase / R2 budget fixture~~ → closed（CI + Postgres 実測；full-scale R2 extrapolation は warn 超過 → 有料移行 gate 要検討）
5. ~~Phase 4.5 gate SSOT~~ → closed

**次ゲート:** Phase 5。ADR-005 **live_gate_005 CLOSED**（9/1 drain + capacity remeasure PASS。証拠 `adr005_live_gate_sept1_drain_20260901.json` / `adr005_capacity_remeasure_20260901.json`）。Phase 4.5 live_gate_45c は waiver closed。詳細: [adr005_gate_status.yaml](adr005_gate_status.yaml)。

推奨 rollout:

1. **4.5-0 contract / feasibility:** gate SSOT、budget contract、`put-fixed` defect、5年 backfill PoC。Secrets-free、本番 I/O なし。
2. **4.5-1 pure metrics:** metric canonicalization、RS75 / Perfect Order 等を small PR 化、serial / parallel equivalence。
3. **4.5-2 snapshot shadow:** R2 shadow prefix、manifest / logical digest。active pointer なし。
4. **4.5-3 registry / series shadow:** DDL、RLS、service-role-only RPC、active CAS、series / latest projection。
5. **4.5-4 required / cutover:** backfill 比較、active CAS、budget monitoring、normal / replay / reconcile live 証拠、3営業日 soak。

Phase 4.5 gate は CLOSED（user-authorized waiver 2026-08-29）。連続 3 営業日 Path B soak 達成とは書かない（8/26 Cron miss）。Path B は active。

## ADR-005（Monthly new-Core backfill、Adopted / live_gate closed）

[ADR-005](../adr/adr-005-monthly-new-core-backfill.md) は、月次で Core に昇格した銘柄の OHLCV と active Web series を非同期補完する設計契約である。**Adopted（2026-08-29）。** Phase 4.5 gate は closed。実装ゲート SSOT は [adr005_gate_status.yaml](adr005_gate_status.yaml)（`overall_status: closed`、`pr_gates` merged via [PR #159](https://github.com/kuwatajunichi-cyber/stockradarsystem/pull/159)、`live_gate_005` closed）。

## Phase 5（entitlements / Web API / observability）

ゲート正本: [phase5_gate_status.yaml](phase5_gate_status.yaml)（`overall_status: in_progress`）。5.5a live close だけでは overall を closed にしない。Issue #93 は **OPEN**。Web UI 完了とは書かない。

Web UI 仕様の前に終わる工事（A / B）と、仕様後の製品工事（C / D / E）に分ける。

| トラック | 現行番号 | 中身 | Web UI 仕様 |
|----------|----------|------|-------------|
| **トラック A** 運用観測 | 5.5a / 5.5b | Healthchecks.io（Patch + Daily）、`runs` 集計ビュー（ops SQL。画面ではない） | 不要 |
| **トラック B** 配信 capability | 5.4 の一部 | private R2、committed のみ、短命署名、監査。製品ロールなし。P0 継承（RLS ON、anon/authenticated REVOKE、公開 mint 禁止） | 不要 |
| **トラック C** 認可製品 | 5.1–5.3 | Supabase Auth、entitlements、課金 webhook、利用者別 RLS | 要る |
| **トラック D** Web UI | ロードマップ外（ADR-004 の消費者） | 銘柄×年 series の閲覧 | これ自体が仕様 |
| **トラック E** 配布切替 | 5.6 | `published/` 統一。live TARGETS（R2 / Dropbox、任意 Drive）を壊さない | 要る |

**Observability 採用（2026-07-08）:** 方針 C。[phase5_observability_cutover.md](phase5_observability_cutover.md)  
カレンダー契約（実装より先に改訂）: `closed_day_expected_ping`。Period 1d × 閉場日非 ping のまま 5.5a を実装しない。  
**監視対象外:** `is_replay=true`, `skip_publish=true`（ping 送信しない）。閉場日 ping とは別契約。  
**Watchdog**（[cron_dispatch_watchdog.md](../contracts/cron_dispatch_watchdog.md)）は Healthchecks の代替ではない。Watchdog = Cloudflare 欠走の当日検知。Healthchecks = GHA 成功の長めネット。両方残す。

P2 は形式ゲートなしの残債。5.5a の blocker にしない。Auth/API 本実装と Issue #93 close は UI 仕様後（トラック C–E）。

## 受け入れ条件

AC-1,5,6,7,10 完了。AC-9→Phase5。AC-2,3,4,8 部分。Phase 4 後監査の P0 gate CLOSED（2026-07-16）。P1 gate CLOSED（2026-07-17）。

## Ops Hardening

Worker deploy gate, migration 記録, artifact_index.created_at_utc, contract stage dict。

## 改訂履歴

2026-07-08 初版。
2026-07-15 Phase 4 gate CLOSED および post-gate 監査・是正順序を追記。
2026-07-22 Phase 4 gate 監査是正（PR-4-2 merge CI 失敗記録・corrective evidence 追加）および P1 closed 反映。
2026-07-22 Phase 4.5 を Free-first R2 / Supabase split に改訂。条件付き GO、実装未着手、preflight blocker を明記。
2026-08-28 ADR-005 を隣接 Proposed として追記。Phase 4.5 テーブル行は不変。
2026-08-29 Phase 4.5 live_gate_45c user-authorized waiver close。ADR-005 Adopted。Issue #93 は Phase 5 / ADR-005 実装のため OPEN。
2026-09-01 ADR-005 live_gate_005 CLOSED（Sept drain + capacity remeasure PASS）。
2026-09-04 SSOT ドリフト是正。Issue #93 の残は Phase 5 のみ。P2 は形式ゲートなしの残債と明記。連続 soak 達成とは書かない。
2026-09-04 Phase 5 をトラック A–E に分割。gate SSOT `phase5_gate_status.yaml`。cutover 休場日を `closed_day_expected_ping` に改訂。5.5a ping は未実装。
2026-09-05 U-55a-1/2 完了。5.5a ping を workflow に組み込み（未マージ・live gate 未達）。

## 決定事項（2026-07-08 追記）

| 項目 | 決定 |
|------|------|
| Phase 4 契約 PR | **Phase 3c gate CLOSED 後**に着手（soak 中は待つ） |
| runs lifecycle 更新 | **workflow 最終 job**（`render_and_upload` 想定）が 1 回 PATCH で success/failed/cancelled を確定 |
