# Issue #93 ロードマップ（正本）

GitHub Issue: [#93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)

**改訂日:** 2026-07-08  
**SSOT:** 詳細正本。Issue #93 本文は要約 + リンク。

設計根拠: [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md)

## フェーズ状態

| Phase | テーマ | 状態 |
|-------|--------|------|
| 0-2c | 契約 / Cron / R2 artifact bus | 完了 |
| 3c | warm cache + Supabase | gate IN PROGRESS |
| 4 | 月次 + publish + runs + Cron | 計画確定 |
| 4.5 | 派生 warm cache | ADR-004 |
| 5 | entitlements + observability | 計画 |

Phase 3 残: soak 3+ 営業日、delisting gate、runbook CLOSED。

## Phase 4（2026-07-08 決定: 単体フェーズ）

In: monthly_snapshots, daily/patch 月次解決切替, publish_status, runs lifecycle, monthly Cron, cache-jpx-url。  
Out: 派生 cache(4.5), auth(5), published/統一(5), cleanup Cron(5+)。  
詳細: [phase4_cutover.md](phase4_cutover.md)

## Phase 5（entitlements / Web API / observability）

| 項目 | 内容 |
|------|------|
| 5.1–5.4 | Auth/RLS, entitlements, webhook, 公開 API |
| **5.5a observability** | **Healthchecks.io heartbeat（採用）** — メール通知。Patch + Daily 各 1 check |
| 5.5b | Supabase 集計ビュー（Phase 4 `runs` 後） |
| 5.6 | Distribution cutover |

**Observability 採用（2026-07-08）:** 方針 C。[phase5_observability_cutover.md](phase5_observability_cutover.md)  
**監視対象外:** `is_replay=true`, `skip_publish=true`（ping 送信しない）。

## 受け入れ条件

AC-1,5,7,10 完了。AC-6→Phase4。AC-9→Phase5。AC-2,3,4,8 部分。

## Ops Hardening

Worker deploy gate, migration 記録, artifact_index.created_at_utc, contract stage dict。

## 改訂履歴

2026-07-08 初版。

## 決定事項（2026-07-08 追記）

| 項目 | 決定 |
|------|------|
| Phase 4 契約 PR | **Phase 3c gate CLOSED 後**に着手（soak 中は待つ） |
| runs lifecycle 更新 | **workflow 最終 job**（`render_and_upload` 想定）が 1 回 PATCH で success/failed/cancelled を確定 |
