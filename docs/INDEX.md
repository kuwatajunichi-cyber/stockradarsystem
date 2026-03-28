# Documentation Index

本リポジトリの設計・判断ドキュメントの正規インデックス。
本プロジェクトに関する議論・レビュー・共同作業は、原則このページを起点とする。

---

## Single Source of Truth

### MVP Design Document
- Version: v1.2
- View (GitHub):  
  https://github.com/kuwatajunichi-cyber/stockradarsystem/blob/main/docs/MVPdesignDoc_v1.2.md
- Raw (Plain text):  
  https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/main/docs/MVPdesignDoc_v1.2.md

### User Story Map
- Version: v1.1
- View (GitHub):  
  https://github.com/kuwatajunichi-cyber/stockradarsystem/blob/main/docs/MVPuserstorymap_v1.1.md
- Raw (Plain text):  
  https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/main/docs/MVPuserstorymap_v1.1.md

### OHLC 記述子・JPX 制限値幅（実装仕様の正）
- [docs/OHLC_desripter_v1.2.md](OHLC_desripter_v1.2.md) — ローソク形状・ラベル・閾値（`candle_descriptor` と整合）
- [docs/JPX_limitTable.md](JPX_limitTable.md) — 制限値幅表（`config/jpx_limit_table.yaml` と対応）

---

## ユーザー向け仕様説明（実装・テンプレを受けた説明用）

**設計正本ではない**。現行のコード・設定・XLSX テンプレートを前提に、エンドユーザー向けの説明・記事用に整備したドキュメント。一覧と置き場所の方針は次を参照。

- **ディレクトリ（View）**:  
  https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/user-facing-spec/
- **目次・説明**: [docs/user-facing-spec/README.md](user-facing-spec/README.md)

### 代表ドキュメント
- ユニバース・指標（v1.1）: [docs/user-facing-spec/universe_and_indicators_v1.1.md](user-facing-spec/universe_and_indicators_v1.1.md)
- 日次レポート XLSX テンプレ（v1.2）: [docs/user-facing-spec/indicators_template_v1.2_design.md](user-facing-spec/indicators_template_v1.2_design.md)
- 価格挙動の読み方: [docs/user-facing-spec/price_behavior_judgement_guide.md](user-facing-spec/price_behavior_judgement_guide.md)
- 旧ユニバース・指標（archive）: [docs/archive/universe_and_indicators_v1.0.md](archive/universe_and_indicators_v1.0.md)

---

## Decision Records

### Architecture Decision Records (ADR)
- Directory (View):  
  https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/adr/
- ADR-001 監査用トレーサビリティ（温存・削除判断）:  
  [docs/adr/adr-001-audit-retention-and-removal.md](adr/adr-001-audit-retention-and-removal.md)

### Decision Candidates (Pre-ADR)
- Directory (View):  
  https://github.com/kuwatajunichi-cyber/stockradarsystem/tree/main/docs/decision-candidates/
- 001 (Raw):  
 https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-001-boro-universe.md
- 002 (Raw):  
 https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-002-rise-mid-down-universe.md
- 003 (Raw):  
 https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/decision-candidates/dc-003-weekly-monthly-report.md

---

## 運用ルール（重要）
- 個別ドキュメントのURL共有は不要  
- 本 INDEX の URL のみ共有すれば十分  
- ChatGPT / 共同作業者は本 INDEX から辿る
