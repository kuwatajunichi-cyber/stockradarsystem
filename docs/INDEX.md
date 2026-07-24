# Documentation Index

本リポジトリの設計・判断ドキュメントの正規インデックス。
本プロジェクトに関する議論・レビュー・共同作業は、原則このページを起点とする。

---

## Single Source of Truth

### MVP Design Document

- Version: v1.2
- View (GitHub):  
  <https://github.com/kuwatajunichi-cyber/stockradarsystem/blob/main/docs/MVPdesignDoc_v1.2.md>
- Raw (Plain text):  
  <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/main/docs/MVPdesignDoc_v1.2.md>

### User Story Map

- Version: v1.1
- View (GitHub):  
  <https://github.com/kuwatajunichi-cyber/stockradarsystem/blob/main/docs/MVPuserstorymap_v1.1.md>
- Raw (Plain text):  
  <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/main/docs/MVPuserstorymap_v1.1.md>

### OHLC 記述子・JPX 制限値幅（実装仕様の正）

- [docs/OHLC_desripter_v1.3.md](OHLC_desripter_v1.3.md) — ローソク形状・ラベル・閾値（`candle_descriptor` と整合）
- [docs/JPX_limitTable.md](JPX_limitTable.md) — 制限値幅表（`config/jpx_limit_table.yaml` と対応）

---

## ユーザー向け仕様説明（実装・テンプレを受けた説明用）

**設計正本ではない**。現行のコード・設定・XLSX テンプレートを前提に、エンドユーザー向けの説明・記事用に整備したドキュメント。一覧と置き場所の方針は次を参照。

- **ディレクトリ（View）**:  
  <https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/user-facing-spec/>
- **目次・説明**: [docs/user-facing-spec/README.md](user-facing-spec/README.md)

### 代表ドキュメント

- ユニバース・指標（v1.2）: [docs/user-facing-spec/universe_and_indicators_v1.2.md](user-facing-spec/universe_and_indicators_v1.2.md)
- 日次レポート XLSX テンプレ（v1.2）: [docs/user-facing-spec/indicators_template_v1.2_design.md](user-facing-spec/indicators_template_v1.2_design.md)
- 価格挙動の読み方: [docs/user-facing-spec/price_behavior_judgement_guide.md](user-facing-spec/price_behavior_judgement_guide.md)
- 旧ユニバース・指標（archive）: [docs/archive/universe_and_indicators_v1.0.md](archive/universe_and_indicators_v1.0.md)

---

## Decision Records

### Architecture Decision Records (ADR)

- Directory (View):  
  <https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/adr/>
- ADR-001 監査用トレーサビリティ（温存・削除判断）:  
  [docs/adr/adr-001-audit-retention-and-removal.md](adr/adr-001-audit-retention-and-removal.md)
- ADR-002 日次 MACD ヒストグラム・チャート寄り状態ラベル:  
  [docs/adr/adr-002-macd-histogram-indicators.md](adr/adr-002-macd-histogram-indicators.md)
- ADR-003 R2 blob plane / Supabase control plane（Issue #93）:  
  [docs/adr/adr-003-r2-supabase-control-blob-split.md](adr/adr-003-r2-supabase-control-blob-split.md)
- ADR-004 派生指標の時系列基盤（Phase 4.5、Free-first R2 / Supabase split）:
  [docs/adr/adr-004-derived-indicators-warm-cache.md](adr/adr-004-derived-indicators-warm-cache.md)

### Decision Candidates (Pre-ADR)

- Directory (View):  
  <https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/decision-candidates/>
- 001 信頼性・実体リスクに基づく調査ルート制御（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-001-boro-universe.md>
- 002 Rise/Mid/Down Universe（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-002-rise-mid-down-universe.md>
- 003 Weekly/Monthly Report（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-003-weekly-monthly-report.md>
- 004 Fake Signal Detector（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-004-fake-signal-detector.md>
- 005 Event Cause Ranking PoC（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-005-event-cause-ranking-poc.md>
- 006 株探/TDNet 取得層の実現性調査（Raw）:  
 <https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-006-external-ingestion-feasibility.md>

---

## 品質ゲート・契約（開発ガバナンス）

CI・ワークフロー・ジョブの変更に関わる「原則」「運用基準」「契約」を階層分離して整理する。詳細は各ファイルの本文に従う。

### Project Rules（Cursor / エディタ向け・原則）

- [.cursor/rules/quality-governance.mdc](../.cursor/rules/quality-governance.mdc)

### Policies（運用基準・レビュー観点）

- [docs/policies/quality-gate-standards.md](policies/quality-gate-standards.md)
- [docs/policies/quality-change-checklist.md](policies/quality-change-checklist.md)

### Contracts（仕様レベルの約束事）

- [docs/contracts/exit_codes.md](contracts/exit_codes.md)
- [docs/contracts/datetime_normalization.md](contracts/datetime_normalization.md)
- [docs/contracts/determinism_and_idempotency.md](contracts/determinism_and_idempotency.md)
- [docs/contracts/workflow_preflight_contract.md](contracts/workflow_preflight_contract.md)
- [docs/contracts/daily_replay_and_monthly_universe.md](contracts/daily_replay_and_monthly_universe.md) — 日次 replay / patched cache / `daily.yml` の artifact・cache 契約

### 補助（スコープ・テスト配置）

- [docs/plans/quality_gate_scope_lock.md](plans/quality_gate_scope_lock.md)
- [tests/TEST_RELOCATION_MAP.md](../tests/TEST_RELOCATION_MAP.md)

### Issue #93 移行ロードマップ（インフラ）

- **正本（詳細）:** [docs/operations/issue_93_roadmap.md](operations/issue_93_roadmap.md)
- Phase 4 後監査・是正計画: [issue_93_post_phase4_audit.md](operations/issue_93_post_phase4_audit.md)
- Phase runbooks: [phase2c](operations/phase2c_r2_only_cutover.md), [phase3](operations/phase3_warm_cache_supabase_cutover.md), [phase4](operations/phase4_cutover.md), [phase4.5](operations/phase4_5_cutover.md)
- Phase 4.5 gate SSOT: [phase4_5_gate_status.yaml](operations/phase4_5_gate_status.yaml)
- Phase 5 observability 調査: [phase5_observability_options.md](operations/phase5_observability_options.md)
- Phase 5 observability runbook: [phase5_observability_cutover.md](operations/phase5_observability_cutover.md)
- GitHub Issue: [#93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)

---

## 運用ルール（重要）

- 個別ドキュメントのURL共有は不要  
- 本 INDEX の URL のみ共有すれば十分  
- ChatGPT / 共同作業者は本 INDEX から辿る
