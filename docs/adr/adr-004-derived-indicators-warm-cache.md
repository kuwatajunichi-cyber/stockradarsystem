# ADR-004: 派生指標の時系列基盤（Free-first R2 / Supabase split）

## 状態

採用・設計改訂済み（2026-07-22）。Phase 4.5 実装は **rollout 4.5c・Path B active・`live_gate_45c` closed**（user-authorized waiver 2026-08-29; continuous 3 trading-day Path B soak is **not** claimed）。「実装は未着手」ではない。

[ADR-005](adr-005-monthly-new-core-backfill.md)（Monthly new-Core backfill）は **Adopted**（docs）。実装ゲートは `docs/operations/adr005_gate_status.yaml`（`in_progress` / `live_gate_005` open）。本 ADR の 4.5c gate CLOSED と混同しない。

Issue #93 Phase 4.5 として Phase 4 live gate 後、Phase 5 の Web API 本格実装前に進める。初版の「単一派生 zip を固定 key へ上書きする」案は、本改訂で置き換える。

## 文脈

### 現行

| レイヤ | 保管 | 中身 | 更新者 |
|--------|------|------|--------|
| Layer 1 warm cache | R2 `index-store-zip-v1` / `ohlc-store-zip-v2` | yfinance 由来の原材料 OHLC(V)・指数 | `ensure_index_cache` / `ensure_core_cache` |
| Run artifact bus | R2 `runs/daily/{run_id}/artifacts/...` | 同一 run 内 handoff、日次断面 CSV | producer job |
| Control plane | Supabase | run、artifact/cache index、publish metadata | storage adapter / RPC |

RS、出来高 zscore、移動平均比等は `compute_indicators_for_core` が毎 run 原材料から再計算する。成果物は `indicators_YYYYMMDD.csv`（1 日×全銘柄の断面）であり、銘柄別の長期派生系列は永続化されていない。

### 新しい要求

- 75 日移動平均、RS、Perfect Order 維持日数等の指標を継続的に追加・変更・廃止する。
- RS 等を銘柄別に数百営業日表示するインタラクティブ Web UI を Phase 5 で実装する。
- 指標の式・窓長・欠損規則を変更しても、旧結果を監査できる。
- 利用者が内部または少数の間は、Supabase / R2 の無料枠を優先し固定費を発生させない。
- 利用者増加時は、API 契約や指標 ID を変えずに有料構成へ拡張できる。

### Free-first 制約

2026-07-22 時点の公開料金を設計基準とする。

- Cloudflare R2 Standard: 10 GB-month、Class A 100 万回/月、Class B 1,000 万回/月まで無料。egress は無料。
- Supabase Free: database 500 MB、egress 5 GB/月、MAU 50,000 を上限目安とする。
- 無料枠はサービス仕様で変更され得るため、実装時と四半期ごとに再確認する。

全履歴を Supabase の JSONB / EAV 行へ保存すると 500 MB を超える。したがって、柔軟性は「全データを DB に置くこと」ではなく、**指標定義・active version・認可を DB で管理し、大容量系列を R2 に置くこと**で確保する。

## 決定

### 1. 責務分離

| 責務 | 正本 |
|------|------|
| 計算の原典 | Layer 1 原材料 + immutable な指標 version |
| 監査・再構築 | R2 immutable daily snapshot + manifest（当時ユニバース断面の正本）。snapshot に含まれない code×date は [ADR-005](adr-005-monthly-new-core-backfill.md) の committed `series_seed_delta` / `series_repair_delta` を supplementary rebuild source とする |
| Web 時系列配信 | R2 銘柄×年 projection |
| 指標定義・active set・object metadata | Supabase |
| 当日横断スクリーニング・配布 | 既存 `indicators_YYYYMMDD.csv` |
| 無料段階の DB 検索 projection | Supabase の最新断面のみ |

派生系列を単独で「正系」とは呼ばない。派生値は原材料と計算仕様から生成される versioned data product である。R2 daily snapshot は **当時のユニバース断面**の監査・再構築正本、Supabase latest projection は再生成可能な検索用投影とする。補完後の active series **全体**は、snapshot 投影だけでは再現できず、「daily snapshot 投影 + committed seed/repair delta」（ADR-005）である。

### 2. R2 物理配置

#### 監査・再構築用 immutable snapshot

```text
derived-snapshots/
  metric-set={set_version}/
    trade-date={YYYY-MM-DD}/
      indicators-{source_fingerprint}.parquet
      manifest.json
```

- 1 営業日×全銘柄を安定順序で格納する。
- 同じ論理 key に異なる fingerprint を通常処理で上書きしない。
- 過去訂正は reconcile 操作、式変更は新しい metric set version として分離する。

#### Web API 用銘柄系列 projection

```text
derived-series/
  metric-set={set_version}/
    symbol={code}/
      year={YYYY}.json.gz
      manifest.json
```

- API は銘柄・年単位で必要 object のみ読む。
- 応答は日付配列と series 列配列の compact JSON とし、行ごとの指標名反復を避ける。
- Parquet を zip に入れない。単一巨大 zip の download・再圧縮・競合を回避する。
- 通常日次更新では当年 object のみ更新する。snapshot は immutable、series projection は再生成可能とする。

### 3. Supabase に保持するもの

Phase 4.5 無料段階では次だけを保持する。

- `metric_definitions`: 指標の安定 ID、表示名、型、単位、説明、lifecycle。
- `metric_versions`: immutable な式 version、parameters、required inputs、最小履歴、欠損規則、implementation fingerprint。
- `metric_set_versions`: 同一 run で生成する指標 version 集合と `draft|shadow|active|retired` 状態。
- active metric set pointer。
- R2 object metadata、logical digest、source run、commit 状態。
- `latest_derived_observations`: 1 銘柄×active set の最新断面。長期履歴は保持しない。

概念スキーマと I/O 契約は本 ADR の各節を正本とする。DDL は実装 PR で migration として追加し、本 ADR だけを根拠に本番変更しない。

### 4. 指標 versioning

- `metric_key` は論理指標の安定 ID（例: `rs_75_topix`, `perfect_order_days`）。
- 式、窓長、ベンチマーク、調整価格、欠損規則の変更は既存 version を更新せず、新 `metric_version` を発行する。
- 指標追加・削除・version 変更は新 `metric_set_version` を作る。
- 指標削除は `deprecated` と active set からの除外で表現し、監査期間中は定義を物理削除しない。
- canonical JSON の SHA-256 を definition fingerprint とする。ハッシュだけで差分を表現せず、canonical input 自体も保存する。

### 5. rollout と active 切替

1. `draft`: 定義、pure 関数、schema contract を作る。
2. `shadow`: 指定期間を backfill し、既存日次断面との一致・欠損率・容量を検証する。
3. `active`: expected current version を受ける CAS RPC で pointer を切り替える。
4. `retired`: 既定 API から外すが、保持期間中は version 指定で監査可能にする。

active set の in-place 変更は禁止する。CAS 失敗時は再取得して停止し、last-write-wins で上書きしない。

### 6. 更新モード

| モード | active pointer | immutable snapshot | series | latest | 用途 |
|--------|----------------|--------------------|--------|--------|------|
| `normal` | 更新 | 新規日を作成 | 当日 merge | 更新 | Daily |
| `replay` | 不変 | 不変 | 不変 | 不変 | 再現 |
| `backfill` | 不変 | shadow のみ | shadow のみ | 不変 | 新 metric set |
| `reconcile` | 不変 | CAS 訂正 | merge | 条件付き | フル断面の明示訂正 |
| `series_seed` | 不変 | 不変 | 欠落日のみ（ADR-005） | 不変 | 新規 Core 履歴。ADR-005 local_only |
| `series_repair` | 不変 | 不変 | 承認済み coordinate のみ（ADR-005） | 不変 | `value_conflict` 修復。ADR-005 local_only |

`series_seed` / `series_repair` の write_allowed・CAS・delta 物理契約は ADR-005 を正とする。本表の追加は採択同期であり、active writer を有効化しない。

「不足日のみ計算」だけでは過去入力訂正を検出できない。各 snapshot に Layer 1 input fingerprint、metric set fingerprint、source run を保存し、不一致を通常 run で検出した場合は fail-fast して reconcile へ分離する。

### 7. 決定性

同一入力からの**論理結果**の一致を契約とする。

- 行順: `instrument_code`、列順: metric set schema 順。
- 日付、timezone、null / NaN、float serialization を固定する。
- canonical logical payload の SHA-256 を manifest に保存する。
- Parquet codec や writer metadata の差による byte-level hash 差は許容するが、logical digest 差は許容しない。
- `indicators_*.csv` と時系列の同一日値は同じ pure 関数から生成し、unit test で一致を固定する。

### 8. stateful 指標

Perfect Order 維持日数等は次を version 契約に含める。

- 使用する移動平均線と成立順序。
- 同値、休場、売買停止、入力欠損、株式分割調整の扱い。
- 成立初日は 1、継続時は前営業日値 + 1、不成立時は 0。
- 判定不能は 0 にせず `null` + quality flag とする。
- backfill の先頭には最大 lookback と状態計算に必要な warm-up を含める。

### 9. retention

必要な Layer 1 履歴を次で決める。

```text
required_history = max_graph_window + max_metric_lookback + buffer
```

500 営業日の表示、252 営業日の RS、20 日 buffer なら最低 772 営業日が必要であり、現行 730 **暦日**では不足する。初期目標は Layer 1 / derived snapshot とも 5 年とし、データ利用ポリシーと実測容量を確認して確定する。

### 10. 無料枠ガードと有料移行

無料段階:

- Supabase database: 350 MB で warning、400 MB で自動 cleanup / 新規履歴投影停止、500 MB を正常運用上限として使い切らない。
- Supabase は latest projection のみ。時系列レスポンス本体を Supabase egress に流さない。
- R2: 8 GB で warning、9 GB で旧 Web projection cleanup を開始する。
- Free plan の pause / SLA / backup 制約を許容する内部・β利用に限定する。

有料移行条件:

- 外部利用者向け可用性を保証する。
- DB 400 MB、R2 9 GB、Supabase egress 4 GB/月、MAU 40,000 のいずれかを継続的に超える。
- Web API の p95 または batch latency が Free compute の SLO を満たさない。

有料移行後も metric ID、object key、API response contract は維持する。必要なら Supabase に直近 N 年の `derived_observations` projection、materialized view、検索頻度の高い指標の専用列を追加する。無料段階で全履歴 JSONB を先行作成しない。

## 不採用

- 原材料 zip と派生系列の単一アーカイブ統合。
- 全銘柄・全期間の単一 `store.zip` 固定 key 上書き。
- Supabase Free に全履歴 EAV / JSONB を保持。
- 指標ごとの DB 列追加を基本とする wide table。
- version 済みの式・parameter・過去値の in-place 更新。
- 通常 run と reconcile の同一コマンド化。
- R2 `ListObjects` に依存する通常読取り。

## コスト概算

3,000 銘柄、年 250 営業日、30 指標、R2 5 年、4 metric set version の初期想定では、R2 は概ね 2.4〜6 GB で無料枠内。Supabase latest projection と定義・制御面は 500 MB 未満を目標とする。

利用者増加時に全履歴 DB projection を導入する場合、3 年で 225 万行、30 指標 JSONB は index を含め概ね 2.1〜3.6 GB が目安となるため、Supabase Pro / Small 以上へ移行してから行う。価格は実装 gate で再見積もりする。

料金根拠:

- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Supabase pricing](https://supabase.com/pricing)

## Phase 4.5 着手条件

既存条件:

1. Phase 3c live gate + soak 完了。
2. Phase 4 live gate 完了。
3. 原材料 cache 契約が本番相当で安定。
4. Phase 4 post-audit P0 / P1 gate CLOSED。

追加設計条件:

5. 本 ADR の schema、version、replay、reconcile、budget 契約を contract test 化する。
6. 現行 `put-fixed` の誤 cache key 参照を修正し、Fake による idempotency / mismatch test を追加する。ただし派生 snapshot の commit は固定 key 上書きを再利用しない。
7. Layer 1 の 5 年保持について、取得元ポリシー、R2 実測容量、backfill 時間を検証する。
8. Phase 4.5 専用 gate SSOT と rollout stage を実装 PR より先に定義する。

推進判定とリスクは [Issue #93 roadmap](../operations/issue_93_roadmap.md) と [Phase 4 post-audit](../operations/issue_93_post_phase4_audit.md) に記録する。

## ADR-002 との関係

- `indicators_*.csv` の直近 K 営業日ワイド列はレポート・XLSX 向けとして維持する。
- 本 ADR の系列はグラフ API・多段計算向けとする。
- 両者の値は同一 pure 関数から生成し、同じ営業日の値が一致することをテストする。

## 影響範囲

- `src/stockradar/indicators/`: versioned pure 指標関数。
- `src/stockradar/jobs/`: snapshot、series projection、latest projection の生成。
- `src/stockradar/storage/`: immutable commit、CAS、reconcile adapter。
- `supabase/migrations/`: metric registry / active set / latest projection。
- `config/github_state_to_r2_supabase_mapping.yaml`: Phase 4.5 object mapping。
- `.github/workflows/`: shadow / backfill / normal / reconcile の分離。
- `docs/contracts/daily_replay_and_monthly_universe.md`: derived replay 非更新契約。
- テスト: pure、Fake I/O、parallel equivalence、mismatch、budget、workflow contract。

## 参照

- [Issue #93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)
- [ADR-002](adr-002-macd-histogram-indicators.md)
- [ADR-003](adr-003-r2-supabase-control-blob-split.md)
- [Issue #93 roadmap](../operations/issue_93_roadmap.md)
- [Phase 4 post-audit](../operations/issue_93_post_phase4_audit.md)
- [daily replay 契約](../contracts/daily_replay_and_monthly_universe.md)
- [R2 / Supabase mapping](../../config/github_state_to_r2_supabase_mapping.yaml)
- [ADR-005](adr-005-monthly-new-core-backfill.md)（Adopted。series_seed / series_repair; impl local_only）
