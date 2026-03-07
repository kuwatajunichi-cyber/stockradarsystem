# Event Cause PoC 仕様 v0.2（更新版）

## 1. 目的

売買代金急増（`z_turnover_* > threshold`）銘柄について、株探/TDnet由来の候補イベントを集約し、
背景候補を `A/B/C` で判定する。

- A: 構造メタデータ上、一次性・銘柄関連性が強い
- B: 候補はあるがA条件に満たない
- C: 外部要因確認不能（候補なし、または低スコア）

本PoCは**調査候補抽出の補助**であり、投資助言を目的としない。

## 2. ジョブ構成（PoC ジョブ。日次運用では selection_rules 等で接続可能）

1. 取得: `stockradar.jobs.fetch_external_events_for_spikes`
2. スコアリング: `stockradar.jobs.rank_turnover_event_causes`

## 3. 入出力

### 入力
- 指標CSV: `indicators_YYYYMMDD.csv`
- 対象条件: `z_turnover_* > z-threshold`

### 中間出力
- `data/external/events/news_tdnet_events_YYYYMMDD.jsonl`

### 最終出力
- `data/analysis/event_causes_poc/event_cause_summary_YYYYMMDD[_suffix].csv`
- `data/analysis/event_causes_poc/event_cause_candidates_YYYYMMDD[_suffix].csv`

## 4. 取得仕様（確定）

### 4.1 株探
- URL: `https://kabutan.jp/stock/news?code=XXXX&nmode=0&date=YYYYMM00`
- 取得メタデータ:
  - `published_at`（行先頭日時）
  - `source_category`（例: `開示`, `材料`, `テク`, `業績`, `市況`, `注目`, `特集`）
  - `title`
  - `url`（`stock/news?...&b=n...` または `disclosures/pdf/...`）

### 4.2 TDnet
- URL: `https://www.release.tdnet.info/inbs/I_list_XXX_YYYYMMDD.html`
- 取得メタデータ:
  - `published_at`（時刻 + run_date）
  - `code`（5桁末尾`0`は4桁化）
  - `title`
  - `has_xbrl`（XBRL列）
  - `listing_exchange`（上場取引所列）
  - `has_update_history`（更新履歴列）
  - `url`（PDFリンク）

### 4.3 取得フィルタ
- 期間: `run_date - lookback_days` ～ `run_date`
- 当日カットオフ: `--cutoff-time HH:MM`（例: `15:30`）
- 株探カテゴリ除外: `--exclude-kabutan-categories`（既定: `特集,注目`）

### 4.4 重複除外
- 同一イベントキー: `code + published_at + title`
- 重複時の優先:
  1. `tdnet` を優先
  2. 同一ソース同士は `confidence_base` が高い方

## 5. メタデータ付与仕様（現行）

### 5.1 `event_type`（タイトルの軽量ルール）
- 例: `決算短信 -> earnings`, `自己株式取得 -> share_buyback`, `業績予想の修正 -> earnings_revision_up`
- 非該当は `other`
- 注意: ルールの肥大化は避ける方針（将来のLLM/Agent導入で再検討）

### 5.2 `event_scope` / `issuer_specificity`
- `source=tdnet` は `issuer/company`
- 株探の市場総括系（例: 本日の【, 話題株, レーティング日報）を `market/low`
- その他は `issuer/company`

### 5.3 `novelty_level`
- 「訂正」-> `low`
- 「経過」-> `followup`
- それ以外 -> `new`

### 5.4 `event_polarity`
- 文脈依存の誤判定を避けるため、**現行は一律 `neutral`**
- したがって `price_alignment` は実質的に順位差を作らない（v2重みは0）

### 5.5 `originality` / `confidence_base`
- `tdnet`: `primary`, `0.9`
- `kabutan`: `recap`, `0.7`

## 6. スコアリング

## 6.1 v1（従来）
- `time_proximity`, `issuer_specificity`, `material_strength`, `primary_source`, `novelty`, `price_alignment`, `confidence_base`
- 既存比較のため維持

### 6.1.1 `time_proximity` の基準
- 当日: `1.0`
- 1日前: `0.9`
- 2〜5日前: `0.6`
- 6〜20日前: `0.35`
- 21日以上前: `0.1`
- 日付パース失敗: `0.1`
- 未来日: `0.0`（通常はカットオフで流入しない）

## 6.2 v2（メタデータ中心）

`--scoring-mode v2` で有効。

### 6.2.1 v2 中間スコア
- `score_time_proximity`
- `score_source_reliability`（source/originality）
- `score_issuer_specificity`（source + URL種別 + category）
- `score_disclosure_channel`（TDnet/PDF/XBRL/カテゴリ）
- `score_category_signal`（`source_category`）
- `score_document_structure`（XBRL・更新履歴・URL構造）
- `score_name_match`（タイトルに対象銘柄名/別称を含むか）
- `score_confidence_base`
- `score_price_alignment`（v2では重み0）

### 6.2.2 `score_name_match`
- 入力:
  - 指標CSVの `name`
  - `shorten_stock_name(name)` の短縮名
  - `config/kabutan_name_aliases.yaml`（`code -> aliases`）
- 判定:
  - 正規化後に alias をタイトル部分一致できれば `1.0`
  - それ以外 `0.0`

### 6.2.3 重み（現行）
`config/event_cause_poc.yaml > weights_v2`

- `time_proximity`: `0.22`
- `source_reliability`: `0.16`
- `issuer_specificity`: `0.10`
- `disclosure_channel`: `0.16`
- `category_signal`: `0.12`
- `document_structure`: `0.06`
- `name_match`: `0.16`
- `confidence_base`: `0.02`
- `price_alignment`: `0.00`

### 6.2.4 総合スコア式
`cause_score = Σ(score_i * weight_i)`（小数点6桁丸め）

## 7. 判定ロジック

### 7.1 v1
- `C`: 候補なし or `top_score < decision_threshold`（既定 `0.55`）
- `A`: 上記以外で `top.score_issuer_specificity >= 0.8` かつ `top.score_material_strength >= 0.6`
- `B`: 上記以外

### 7.2 v2
- `C`: 候補なし or `top_score < decision_threshold`
- `A`: `top_score >= a_threshold` かつ
  - `score_disclosure_channel >= 0.75`
  - `score_category_signal >= 0.70`
- `B`: 上記以外

## 8. 比較検証（2026-02-27）

同一入力（`z-threshold=3.5`, `lookback=20`, `cutoff=15:30`, `特集/注目除外`, 重複除去後 152件）で比較。

- v1（`_v1_nm`）: `A=11, B=8, C=1`
- v2 + name_match（`_v2_nm_full`）: `A=1, B=15, C=4`
- 差分:
  - `cause_type` 変更: `13/20`
  - `top_source` 変更: `4/20`

比較ファイル:
- `data/analysis/event_causes_poc/event_cause_summary_compare_20260227_v1_nm_vs_v2_nm.csv`

## 9. 既知課題

1. `event_type` は軽量ルールのため、`other` 偏重が残る
2. 同義タイトル（括弧・記号差）の近似重複は未対応
3. `name_match` は別称辞書品質に依存
4. 時刻はローカル解釈（将来はJST明示統一が望ましい）

## 10. 代表実行コマンド

```powershell
$env:PYTHONPATH = "src"

# 取得
python -m stockradar.jobs.fetch_external_events_for_spikes `
  --run-date 2026-02-27 `
  --indicators "C:/Users/junic/Downloads/indicators_20260227.csv" `
  --z-threshold 3.5 `
  --lookback-days 20 `
  --cutoff-time 15:30 `
  --exclude-kabutan-categories "特集,注目" `
  --output data/external/events/news_tdnet_events_20260227.jsonl

# v2 + name_match
python -m stockradar.jobs.rank_turnover_event_causes `
  --run-date 2026-02-27 `
  --indicators "C:/Users/junic/Downloads/indicators_20260227.csv" `
  --events-jsonl data/external/events/news_tdnet_events_20260227.jsonl `
  --z-threshold 3.5 `
  --scoring-mode v2 `
  --name-alias-config config/kabutan_name_aliases.yaml `
  --decision-threshold 0.58 `
  --a-threshold 0.72 `
  --output-suffix "_v2_nm_full"
```

## 11. 日次接続（運用拡張）

PoC（手動実行）とは別に、日次運用では以下を追加する。

1. `selection_rules` でニュース収集対象銘柄を設定駆動で抽出
   - 既定: `z_turnover_60 > 3.5`
   - 将来拡張: `z_turnover_60 < -3.5`、`candle_labels` の `LIMIT_*` 条件
2. `fetch_external_events_for_spikes` / `rank_turnover_event_causes` は同一 `selection_rules` を参照
3. 指標CSVに `event_news_1_title`, `event_news_1_url`, `event_cause_type` を付与した render 用CSVを生成
4. `cause_type=C` は `event_news_1_title="材料不明・需給起因疑い"` を設定し、`event_news_1_url` は空
5. ニュース付与ワークフローが失敗しても、従来の指標CSVで日次レポート出力を継続（フェイルソフト）
