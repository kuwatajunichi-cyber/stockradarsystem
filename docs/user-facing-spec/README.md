# ユーザー向け仕様説明（`user-facing-spec`）

このディレクトリは **設計の正本（single source of truth）ではありません**。  
`config/`・`src/`・テンプレート XLSX など **現行実装・成果物を正**とし、それを受けて **エンドユーザー向けの説明・ランディング・解説記事用の情報源**として整備した Markdown を置きます。

- 実装やテンプレートを変更したら、対応する説明ドキュメントの更新を検討してください。
- プロダクト設計の意思決定そのものは `docs/MVPdesignDoc_v1.2.md` や ADR 等を参照してください。
- **ローソク記述子・制限値幅の設計正本**は `docs/` 直下の [OHLC_desripter_v1.2.md](../OHLC_desripter_v1.2.md) と [JPX_limitTable.md](../JPX_limitTable.md)（本ディレクトリには置かない）。

## 収録ファイル（例）

| ファイル | 内容の目安 |
| -------- | ---------- |
| [universe_and_indicators_v1.1.md](universe_and_indicators_v1.1.md) | ユニバース・指標の平易な説明と、日次 XLSX との表示対応 |
| [indicators_template_v1.2_design.md](indicators_template_v1.2_design.md) | 日次レポート用テンプレートの列・見出し・条件付き書式などの説明 |
| [price_behavior_judgement_guide.md](price_behavior_judgement_guide.md) | 価格挙動（文言・判定）の読み方ガイド |
| [externalLink_v1.0.md](externalLink_v1.0.md) | 外部サイトリンクの役割と URL 規則 |
| [RS_advanced_v1.0.md](RS_advanced_v1.0.md) | RS 関連の補足説明 |

インデックスからの入口: [docs/INDEX.md](../INDEX.md)
