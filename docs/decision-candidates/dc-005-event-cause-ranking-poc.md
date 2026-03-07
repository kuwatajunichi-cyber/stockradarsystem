# dc-005: 売買代金急増の背景候補ランキング（PoC）

## 目的

`z_turnover_* > 4` の銘柄に限定して、株探ニュースと TDNet から
「背景候補」を抽出し、A/B/C で分類する。

- A: 明示的材料あり（銘柄固有かつ材料強度が高い）
- B: 間接的材料あり（セクター・テーマ等）
- C: 外部要因確認不能（候補なし or スコア不足）

## 非目標（安全策）

- 既存の日次/月次ワークフローへの組み込みはしない
- 既存成果物（`data/indicators/daily` や render 出力）を上書きしない
- 売買推奨はしない（調査候補の補助情報に限定）

## 実装位置

- Pureロジック: `src/stockradar/event_causes/scoring.py`
- 実験ジョブ: `src/stockradar/jobs/rank_turnover_event_causes.py`
- 設定: `config/event_cause_poc.yaml`
- 出力先: `data/analysis/event_causes_poc/`

## 入力

1) 指標CSV  
`data/indicators/daily/indicators_YYYYMMDD.csv`

2) 外部イベントJSONL（手動・別処理で準備）  
既定: `data/external/events/news_tdnet_events.jsonl`

### JSONL の1行例

```json
{
  "code": "7203",
  "source": "tdnet",
  "published_at": "2026-03-06T15:30:00+09:00",
  "title": "自己株式取得に係る事項の決定に関するお知らせ",
  "raw_text_short": "取得総額上限...",
  "event_type": "share_buyback",
  "event_polarity": "positive",
  "issuer_specificity": "company",
  "novelty_level": "new",
  "expected_impact_horizon": "short",
  "confidence_base": 0.95,
  "event_scope": "issuer",
  "originality": "primary"
}
```

## 実行例

```powershell
$env:PYTHONPATH = "src"
# 1) 株探/TDnet からイベント候補を自動取得してJSONL化
python -m stockradar.jobs.fetch_external_events_for_spikes --run-date 2026-03-06 --z-threshold 4.0 --lookback-days 20

# 2) 候補をスコアリングしてA/B/C分類
python -m stockradar.jobs.rank_turnover_event_causes --run-date 2026-03-06
```

## 出力

- `event_cause_summary_YYYYMMDD.csv`
  - 銘柄単位の最終判定（A/B/C、top_score、top_title など）
- `event_cause_candidates_YYYYMMDD.csv`
  - 候補イベント単位の詳細スコア内訳

## スコア要素（PoC）

- 時間近接
- 銘柄固有性
- 材料強度
- 一次性（source/originality）
- 新規性
- 値動き整合
- 基礎信頼度

## 既知の制約

- 営業日カレンダー厳密対応ではなく日付差ベース
- 株探/TDNet 取得自体はこの PoC の対象外（入力前提）
- 因果推定ではなく「候補順位付け」
