# Phase 4.5 cutover runbook

正本: [issue_93_roadmap.md](issue_93_roadmap.md)  
**ゲート証拠 SSOT:** [phase4_5_gate_status.yaml](phase4_5_gate_status.yaml)

## スコープ

Phase 4.5 preflight blocker 解消（実装着手前ゲート）。本番 writer / active cutover は 4.5-4 以降。

## 前提

- Phase 3c / Phase 4 gate CLOSED（[phase4_gate_status.yaml](phase4_gate_status.yaml)）
- P0 / P1 hardening CLOSED（[issue_93_post_phase4_audit.md](issue_93_post_phase4_audit.md)）

## PR 分割（preflight）

| PR Gate ID | 内容 |
|------------|------|
| pr-45-0-gate-ssot | SSOT YAML、honesty、rollout off、cutover runbook |
| pr-45-0b-put-fixed | cache_bus_cli L107 修正 + Fake regression |
| pr-45-0c-layer1-poc | config API、archive pure、long-history module、PoC script |
| pr-45-0d-budget | pyarrow、fixture generator、threshold tests、Postgres 実測証拠 |
| pr-45-0e-registry | 004/005 DDL、RLS、CAS RPC、Protocol/Fake |

## Rollout stage

| Stage | 書込み |
|-------|--------|
| off | 派生 writer なし（preflight 初期値） |
| 4.5a | R2 snapshot shadow のみ |
| 4.5b | + registry metadata、series shadow |
| 4.5c | normal のみ active/latest 更新 |

Phase 4 gate SSOT（phase4_gate_status.yaml）は変更しない。

## Live gate 4.5c（4.5-4 以降）

`live_gate_45c` を close するには、**4.5-1〜4.5-4 の実装完了後**に以下の live run 証拠 URL を記録する。

| 証拠キー | 意味 |
|----------|------|
| `normal_daily_success_run_url` | rollout `4.5c` + mode `normal` で daily 成功 |
| `replay_no_shared_mutation_run_url` | replay が derived shared 状態を更新しない |
| `backfill_shadow_only_run_url` | backfill が shadow のみ更新 |
| `reconcile_isolated_run_url` | reconcile 専用 entrypoint で isolated 訂正 |

加えてロードマップ上は **3 営業日 soak**（`soak_run_urls`）が必要。

**前提（未達のため live gate は open 維持）:**

- `daily.yml` 等に `PHASE4_5_ROLLOUT_STAGE` / derived writer ステップが未配線
- mapping `phase4_5_rollout_stage: "off"`
- 本番 Supabase 004/005 DDL apply 済み（2026-08-12）だが writer / CAS adapter 未接続

**推奨実行順:** 4.5-1 pure metrics → 4.5-2 shadow → 4.5-3 registry shadow → 4.5-4 cutover → rollout `4.5c` → live 証拠取得。
