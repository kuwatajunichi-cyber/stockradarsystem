# Phase 4.5 cutover runbook

正本: [issue_93_roadmap.md](issue_93_roadmap.md)  
**ゲート証拠 SSOT:** [phase4_5_gate_status.yaml](phase4_5_gate_status.yaml)

## スコープ

Phase 4.5 の cutover / live gate 運用。preflight blocker（4.5-0）は closed。実装 PR-45-1..4 と rollout 4.5c は main 済み。残ゲートは **live_gate_45c**（Path B 13209d23 は active、post-CAS 3営業日 soak 未達のため open）。capacity_gate は Path B v2 safety 1.20 で closed。

## 前提

- Phase 3c / Phase 4 gate CLOSED（[phase4_gate_status.yaml](phase4_gate_status.yaml)）
- P0 / P1 hardening CLOSED（[issue_93_post_phase4_audit.md](issue_93_post_phase4_audit.md)）
- preflight blockers 5/5 closed（[phase4_5_gate_status.yaml](phase4_5_gate_status.yaml)）

## PR 分割（preflight・履歴）

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
| 4.5c | normal のみ active/latest 更新（**現行 mapping**） |

Phase 4 gate SSOT（phase4_gate_status.yaml）は変更しない。

## Live gate 4.5c

live_gate_45c を close するには、以下の live run 証拠 URL と **3 営業日 soak**（soak_run_urls）が必要。進捗正本は gate_status。

| 証拠キー | 意味 |
|----------|------|
| 
ormal_daily_success_run_url | rollout 4.5c + mode 
ormal で daily 成功 |
| 
eplay_no_shared_mutation_run_url | replay が derived shared 状態を更新しない |
| ackfill_shadow_only_run_url | backfill が shadow のみ更新 |
| 
econcile_isolated_run_url | reconcile 専用 entrypoint で isolated 訂正 |

**現状（live_gate_45c open / Path B active）:**

- mapping phase4_5_rollout_stage: "4.5c"。daily.yml derived writer は本番書込中
- normal / replay / backfill / reconcile の live URL は gate_status に記録済み。soak_run_urls の 3 URL は **CAS 前の placeholder active set** の daily であり、Path B soak には使えない。live_gate は open 維持
- 4.5a/4.5b は mapping phase4_5_shadow_metric_set_version_id が必須（Fake store 禁止）
- 本番 Supabase **004〜010** DDL apply 済み（007 CAS + 008 batch RPCs + 009 manifest kinds / commit expected_* + 010 commit statement_timeout 180s）。証拠: [phase45_production_ddl_applied.json](evidence/phase45_production_ddl_applied.json)、[phase45_migration_009_applied_2026-08-17.json](evidence/phase45_migration_009_applied_2026-08-17.json)、[phase45_migration_010_applied_2026-08-18.json](evidence/phase45_migration_010_applied_2026-08-18.json)
- Path B catalog は 2026-08-22 に CAS で activate 済み（13209d23-ded6-482d-be08-7da6062013c0）。placeholder 11111111 は retired。証拠: [phase45_aclive_cas_2026-08-22.json](evidence/phase45_aclive_cas_2026-08-22.json)
- 本番 R2 物理キーは `stock-radar-system/<logical>`。GitHub secret `R2_BASE_PREFIX` はバケット名（**末尾スラッシュ禁止**）。`R2_ENDPOINT_URL` は bucket path なし。証拠: [phase45_r2_physical_prefix_2026-08-17.json](evidence/phase45_r2_physical_prefix_2026-08-17.json)
- leftover `derived-shadow/` と failed gen `56004f01` は 2026-08-17 に削除済み。証拠: [phase45_leftover_sweep_2026-08-17.json](evidence/phase45_leftover_sweep_2026-08-17.json)
- Path B set 13209d23 の committed snapshot は直近 60営業日（2026-05-25 … 2026-08-18）+ catchup 8/19–8/21。書込は serial GHA `derived_backfill.yml`（同一 set の日付並列禁止。60日代表 [Backfill #32562373843](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/32562373843)）。CAS 後の current-latest reconcile は 2026-08-21（[Reconcile #32567430829](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/32567430829)、gen `b6e771b5`、logical digest 不変、latest 8/21=2283）。証拠: [phase45_aclive_60d_shadow_backfill_gha_2026-08-22.json](evidence/phase45_aclive_60d_shadow_backfill_gha_2026-08-22.json)、[phase45_aclive_pathb_latest_reconcile_gha_2026-08-21.json](evidence/phase45_aclive_pathb_latest_reconcile_gha_2026-08-21.json)。8/18 soak 監査: [Daily Indicators #32108307197](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/32108307197)
- capacity_gate は closed（Path B v2; safety_factor 1.20, within_free_tier）

**履歴上の推奨実行順（完了済み）:** 4.5-1 pure metrics → 4.5-2 shadow → 4.5-3 registry shadow → 4.5-4 cutover → rollout 4.5c → live 証拠取得。

## Derived writer 性能（008 + 並列 R2）

- Writer は銘柄単位直列 I/O をやめ、committed series の prefetch・並列 R2・500 件チャンク batch RPC を使う（PR #150）。
- 環境変数 DERIVED_R2_CONCURRENCY（既定 32）。boto3 max_pool_connections は同値以上。
- 観測: derived_bus_cli put-generation JSON の series_count / 
2_concurrency / elapsed_ms が daily.yml step summary に出る。壁時計 10 分未満を soak 証拠に使える。

### 失敗後の再実行（重要）

チャンク途中失敗時は ail_generation する（部分 commit なし）。egin_derived_generation は同一 github_run_id の failed を REJECT する。

- **GitHub Actions の Re-run（同一 run id）では回復できない。**
- 失敗後は **新規 workflow run**（workflow_dispatch または翌営業日の schedule）が必要。
