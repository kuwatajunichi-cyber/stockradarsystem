# Phase 4 cutover runbook

正本: [issue_93_roadmap.md](issue_93_roadmap.md)  
**ゲート証拠 SSOT:** [phase4_gate_status.yaml](phase4_gate_status.yaml)（完了報告は本ファイル + CI contract が正本）

## スコープ

4.1 monthly_snapshots + R2 monthly/
4.2 monthly.yml R2/Supabase commit
4.3 daily/patch 月次解決 Supabase/R2
4.4 publish_status + daily publish manifest
4.5 runs lifecycle
4.6 cache-jpx-url R2
4.7 monthly Cron Worker

## Step 4.0 チェックリスト

Phase 3c CLOSED, DDL, mapping, Worker cron, smoke, rollback。

## PR 分割

PR-4-1 DDL, PR-4-2 monthly shadow, PR-4-3 resolve 4b, PR-4-4 publish/runs, PR-4-5 jpx-url, PR-4-6 Cron+4c。

## Rollout

4a GH primary / 4b R2+SB+fallback / 4c Release removed。

## Live gate

4c: Release なし daily success, publish_status committed, runs.status, Cron 記録。

## 決定事項（2026-07-08）

- Phase 4 着手: Phase 3c gate CLOSED 後（契約 PR も同様）
- **runs lifecycle（4.5）**: 最終 job `render_and_upload` が workflow 全体の結論を Supabase に 1 回 PATCH
  - success: 全 required job 成功 + publish 成功（skip_publish 時は publish 除外ルールを契約で定義）
  - failed: いずれか required job 失敗
  - cancelled: GHA cancelled（将来）
  - `resolve_trading_day` の upsert-run（running）は Phase 3 どおり維持
