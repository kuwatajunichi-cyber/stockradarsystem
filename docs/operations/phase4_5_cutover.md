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
