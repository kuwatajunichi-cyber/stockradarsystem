# Issue #93 ロードマップ（正本）

GitHub Issue: [#93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)

**改訂日:** 2026-07-22
**SSOT:** 詳細正本。Issue #93 本文は要約 + リンク。

設計根拠: [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md)、[ADR-004](../adr/adr-004-derived-indicators-warm-cache.md)

## フェーズ状態

| Phase | テーマ | 状態 |
|-------|--------|------|
| 0-2c | 契約 / Cron / R2 artifact bus | 完了 |
| 3c | warm cache + Supabase | **gate CLOSED** (2026-07-10) |
| 4 | 月次 + publish + runs + Cron | **gate CLOSED** (2026-07-22) |
| 4.5 | 派生指標時系列基盤 | **preflight マージ済み（PR #134）・Postgres 実測完了・live gate 4.5c 未達・rollout off** |
| 5 | entitlements + observability | 計画 |

Phase 3c gate CLOSED（runbook 記録済）。Issue #93 は Phase 4.5/5 が残るため **OPEN** 維持。残: delisting effective-day gate（任意）。

## Phase 4 後監査と是正順序（2026-07-15）

詳細: [issue_93_post_phase4_audit.md](issue_93_post_phase4_audit.md)

| 優先度 | タイミング | 内容 |
|--------|------------|------|
| **P0** | **即時・Phase 4.5 前** | **gate CLOSED** (2026-07-16): Supabase 6表の RLS / table privilege、`SECURITY DEFINER` RPC の匿名実行権限を hardening |
| **P1** | **Phase 4.5 着手ゲート** |**gate CLOSED** (2026-07-17): terminal semantics、GHA/Supabase 結論一致、stale `running`、publish mismatch fail-fast|
| **P2** | Phase 4.5 と同時 | bus CLI Fake test、daily publish/finalize 契約、storage mypy、migration baseline |
| **P3** | Phase 5 | Auth/entitlement に基づく細粒度 RLS、API、heartbeat、distribution |

P0 は現在の匿名変更可能性を遮断する防御であり、Phase 5 の利用者別認可とは分離する。P0 gate CLOSED（2026-07-16）。P1 gate CLOSED（2026-07-17）。Phase 4.5 は契約・PoC・pure logic へ着手可能。本番 writer / active cutover は下記 preflight 完了まで未承認。

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

現時点の blocker:

1. Layer 1 の5年保持・backfill 実現性検証。
2. 現行 `put-fixed` の誤 cache key 参照修正と Fake idempotency test。
3. metric registry / RLS / active CAS の DDL 契約。
4. Supabase / R2 budget の fixture 実測。
5. Phase 4.5 専用 gate SSOT。

推奨 rollout:

1. **4.5-0 contract / feasibility:** gate SSOT、budget contract、`put-fixed` defect、5年 backfill PoC。Secrets-free、本番 I/O なし。
2. **4.5-1 pure metrics:** metric canonicalization、RS75 / Perfect Order 等を small PR 化、serial / parallel equivalence。
3. **4.5-2 snapshot shadow:** R2 shadow prefix、manifest / logical digest。active pointer なし。
4. **4.5-3 registry / series shadow:** DDL、RLS、service-role-only RPC、active CAS、series / latest projection。
5. **4.5-4 required / cutover:** backfill 比較、active CAS、budget monitoring、normal / replay / reconcile live 証拠、3営業日 soak。

このため Phase 4.5 を completed / CLOSED と報告しない。契約・PoC・shadowから段階導入する。

## Phase 5（entitlements / Web API / observability）

| 項目 | 内容 |
|------|------|
| 5.1–5.4 | Auth/RLS, entitlements, webhook, 公開 API（派生系列は Phase 4.5 の R2 series contract を利用） |
| **5.5a observability** | **Healthchecks.io heartbeat（採用）** — メール通知。Patch + Daily 各 1 check |
| 5.5b | Supabase 集計ビュー（Phase 4 `runs` 後） |
| 5.6 | Distribution cutover |

**Observability 採用（2026-07-08）:** 方針 C。[phase5_observability_cutover.md](phase5_observability_cutover.md)  
**監視対象外:** `is_replay=true`, `skip_publish=true`（ping 送信しない）。

## 受け入れ条件

AC-1,5,6,7,10 完了。AC-9→Phase5。AC-2,3,4,8 部分。Phase 4 後監査の P0 gate CLOSED（2026-07-16）。P1 gate CLOSED（2026-07-17）。

## Ops Hardening

Worker deploy gate, migration 記録, artifact_index.created_at_utc, contract stage dict。

## 改訂履歴

2026-07-08 初版。
2026-07-15 Phase 4 gate CLOSED および post-gate 監査・是正順序を追記。
2026-07-22 Phase 4 gate 監査是正（PR-4-2 merge CI 失敗記録・corrective evidence 追加）および P1 closed 反映。
2026-07-22 Phase 4.5 を Free-first R2 / Supabase split に改訂。条件付き GO、実装未着手、preflight blocker を明記。

## 決定事項（2026-07-08 追記）

| 項目 | 決定 |
|------|------|
| Phase 4 契約 PR | **Phase 3c gate CLOSED 後**に着手（soak 中は待つ） |
| runs lifecycle 更新 | **workflow 最終 job**（`render_and_upload` 想定）が 1 回 PATCH で success/failed/cancelled を確定 |
