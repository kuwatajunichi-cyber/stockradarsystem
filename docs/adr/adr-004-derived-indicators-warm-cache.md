# ADR-004: 算出指数（派生指標）の Warm Cache 化

## 状態

採用（2026-07。実装は Issue #93 **Phase 4 完了後・Phase 5 着手前** の独立フェーズとする。詳細 DDL は着手直前に config/github_state_to_r2_supabase_mapping.yaml へ反映する）

## 文脈

### 現行の二層構造

| レイヤ | 保管 | 中身 | 更新者 |
|--------|------|------|--------|
| **Warm Cache** | index-store-zip-v1 / ohlc-store-zip-v2 | yfinance 由来の **原材料** OHLC(V) | ensure_index_cache / ensure_core_cache |
| **Run artifact bus** | R2 
uns/daily/{run_id}/artifacts/... | 同一 run 内 handoff（断面 CSV 等） | producer job |

Phase 3（[ADR-003](adr-003-r2-supabase-control-blob-split.md)）は原材料 Warm Cache の R2+Supabase 移行と run artifact bus の維持を行うが、**原材料の二重経路（cache + artifact）は解消しない**。

### 算出指数の現状

- RS・出来高 zscore・移動平均比等は compute_indicators_for_core が **毎 run 原材料から再計算** する。
- 成果物は indicators_YYYYMMDD.csv（**1 日×全銘柄の断面**ワイド表）として run artifact daily-indicators-{run_date} で受け渡す。
- **銘柄ごとの派生指標時系列**（過去 N 営業日分の RS や MA 等）は Warm Cache にも永続成果物にも存在しない。

### 将来需要

- **グラフ描画**（Phase 5 以降の Web / API）: 銘柄ごとに数十〜数百営業日の系列が必要。
- **多段計算**（例: RS → その RS に MACD）: 中間系列の履歴が必要（[ADR-002](adr-002-macd-histogram-indicators.md) の MACD ワイド列と併用）。
- 原材料 Warm Cache 化（Phase 3）とは **別次元** の進化。混同しない。

### 着手タイミングの判断

| 案 | 時期 | 評価 |
|----|------|------|
| Phase 3 直後 | Phase 3c + soak 直後 | **不採用** — R2 移行・replay 契約・mapping の安定化とリスクが重なる |
| **Phase 4.5（本 ADR）** | Phase 4 live gate 後、Phase 5 前 | **採用** — 原材料正系が安定、月次整合の基盤あり、グラフ消費者着手前に系列基盤を用意できる |
| Phase 5 以降 | entitlements / Web 本格化後 | 遅すぎる — 計算コストだけ先行し、API 設計の手戻りが増える |

## 決定

### 採用: 派生指標専用 Warm Cache（Layer 2）

1. 原材料（Layer 1）と **別 zip / 別 cache_key** で派生系列を R2 に増分保存する。
2. 制御面は [ADR-003](adr-003-r2-supabase-control-blob-split.md) 同型: R2 cache/derived-... + Supabase cache_index / cache_pointers。
3. Phase 3 で導入する put-fixed / get-fixed / commit_fixed_cache パターンを **再利用** する（新規バスを増やさない）。
4. 日次断面 CSV（indicators_*.csv）は **当面維持** — 配布・enrichment・既存テンプレとの互換。派生 cache は **時系列の正系** とし、直近 K 日のワイド列（ADR-002）とは役割分担する。
5. replay 時は原材料と同型で **put-fixed をスキップ**（[daily_replay_and_monthly_universe](../contracts/daily_replay_and_monthly_universe.md)）。replay run の当日計算は run スコープ staging で downstream へ handoff する。

### 不採用

- Phase 3 直後の同時着手（移行リスクの重複）。
- 原材料 zip と派生 zip の **単一アーカイブ統合**（更新頻度・スキーマ・replay 契約が異なるため）。
- 派生系列のみ Supabase DB 行保持（ADR-003 の blob/control 分離に反する）。

### cache_key 命名（初期案）

`
cache/derived-{family}-v{schema_version}-{param_hash}/store.zip
`

- amily: 例 core-indicators（RS, zscore, MA 比等の束ね）
- param_hash: 窓長・式バージョン等を含む安定ハッシュ（列定義変更時は新 key）

### 増分更新契約（概要）

- **入力**: Layer 1 原材料 cache（index / ohlc）から当該営業日分を読み、不足日のみ再計算して zip へ追記。
- **冪等性**: 同一 
un_date の再実行は同一バイト列（determinism 契約に従う）。
- **欠損・失敗**: flags / manifest で可視化。静かな縮退は禁止（品質ガバナンス原則）。

## Issue #93 ロードマップへの位置づけ

**Phase 4.5（仮称）** として、Phase 4（月次 Release → R2 monthly/）完了後・Phase 5（entitlements / Web）着手前に挿入する。

着手ゲート（すべて満たしてから実装 PR を開く）:

1. Phase 3c live gate + soak 完了
2. Phase 4 live gate 完了
3. github_state_to_r2_supabase_mapping の原材料 cache 契約が本番相当で安定

## ADR-002 との関係

- **直近 K 営業日**: indicators_*.csv のワイド列（MACD ヒスト等）— レポート・XLSX 向け。
- **長期系列**: 本 ADR の派生 Warm Cache — グラフ API・多段計算向け。
- 両者の数値は同一 pure 関数から生成し、テストで一致を固定する。

## 影響範囲（着手時に更新）

- src/stockradar/jobs/ — 派生 cache ensure / commit ジョブ
- scripts/ — cache_bus_cli 拡張（put-fixed 系の派生 key）
- config/github_state_to_r2_supabase_mapping.yaml — 派生 cache エントリ
- docs/contracts/daily_replay_and_monthly_universe.md — replay 時 put-fixed スキップの明文化（派生 key 追記）
- テスト — Fake cache bus / 純粋増分ロジックの unit

## 参照

- [Issue #93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)
- [ADR-002](adr-002-macd-histogram-indicators.md)
- [ADR-003](adr-003-r2-supabase-control-blob-split.md)
- [daily_replay_and_monthly_universe](../contracts/daily_replay_and_monthly_universe.md)
- [github_state_to_r2_supabase_mapping](../../config/github_state_to_r2_supabase_mapping.yaml)
