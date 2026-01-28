Design Doc v0.2 に対して **実装に直結する追記（v0.3追補）**として、

1. **最小データモデル**（DB/ファイル）

2. **日次バッチのジョブ分割**（初回バックフィル vs 日次差分）  
   をまとめる。

* * *

Design Doc v0.3 追補
==================

最小データモデル & バッチ分割
----------------

* * *

1. 最小データモデル（MVP）

----------------

MVPは「まず1パスを通す」ので、DBは **SQLite（ローカルファイル）** でも良い。  
ただしクラウド実行を前提にするなら、将来の移行を容易にするため、**“テーブル設計はRDB準拠”**で持つ。  
（GitHub Actionsの場合は、実体は `data/` にDBファイル保存→Driveにバックアップでも可）

### 1.1 エンティティ設計（最小）

#### A) `master_snapshots`（JPX月次スナップショット管理）

| カラム            | 型         | 説明                |
| -------------- | --------- | ----------------- |
| snapshot_id    | text (PK) | `JPX_YYYY-MM`     |
| source         | text      | `JPX`             |
| snapshot_month | date      | 月初日など             |
| fetched_at     | datetime  | 取得日時              |
| file_hash      | text      | 内容ハッシュ            |
| status         | text      | `active/archived` |

**目的**

* 「どの月次一覧を使ったか」を固定し、再現性を担保

* * *

#### B) `listings`（銘柄マスター：listing単位）

| カラム                | 型         | 説明                             |
| ------------------ | --------- | ------------------------------ |
| listing_id         | text (PK) | `JPX:XXXX`（4桁）＋区分で一意           |
| ticker             | text      | 例：`XXXX.T`                     |
| name               | text      | 銘柄名                            |
| market             | text      | Prime/Std/Growth等              |
| security_type      | text      | `common/etf/reit/other`        |
| share_class        | text      | `common/classA/classB/unknown` |
| is_primary         | bool      | 主たる普通株か                        |
| listed_date        | date      | 公式上場日（取得できれば）                  |
| first_trade_date   | date      | 推定（yfinance最古等）                |
| listed_date_source | text      | `JPX/inferred/unknown`         |
| status             | text      | `active/delisted/unknown`      |
| created_at         | datetime  |                                |
| updated_at         | datetime  |                                |

**注意**

* 末尾A/Bなどの種類株を別listingとして持つ（混ぜない）

* * *

#### C) `pending_listings`（Pending：JPX未収載の監視）

| カラム                    | 型         | 説明                         |
| ---------------------- | --------- | -------------------------- |
| pending_id             | text (PK) | `MINKABU:...`              |
| detected_at            | datetime  | 検出日時                       |
| minkabu_key            | text      | URLキー等                     |
| code_candidate         | text      | 推定4桁                       |
| name_candidate         | text      | 推定名称                       |
| reason                 | text      | `in_minkabu_not_in_jpx`    |
| resolved_to_listing_id | text      | 昇格時に紐付け                    |
| resolved_at            | datetime  |                            |
| status                 | text      | `pending/resolved/ignored` |

**MVP方針**

* pendingは Core へ混ぜない

* 監視用の別シートに載せるか、ログのみでも良い

* * *

#### D) `daily_bars`（日足：正規化済み）

| カラム         | 型          | 説明                            |
| ----------- | ---------- | ----------------------------- |
| date        | date (PK*) |                               |
| listing_id  | text (PK*) |                               |
| open        | real       |                               |
| high        | real       |                               |
| low         | real       |                               |
| close       | real       |                               |
| volume      | real       |                               |
| source      | text       | `yfinance`                    |
| price_basis | text       | `adjusted/unadjusted/unknown` |
| fetched_at  | datetime   |                               |

※ 主キーは `(date, listing_id)`

* * *

#### E) `universe_memberships`（分母固定：日付×ユニバース）

| カラム         | 型          | 説明                       |
| ----------- | ---------- | ------------------------ |
| date        | date (PK*) |                          |
| universe_id | text (PK*) | 例：`CORE` `IPO` `PENDING` |
| listing_id  | text (PK*) |                          |
| snapshot_id | text       | 参照JPX月次                  |
| reason      | text       | 主要ルールの結果メモ               |
| created_at  | datetime   |                          |

* * *

#### F) `indicator_values`（指標：日付×銘柄）

| カラム            | 型          | 説明                 |
| -------------- | ---------- | ------------------ |
| date           | date (PK*) |                    |
| listing_id     | text (PK*) |                    |
| universe_id    | text       |                    |
| rs_long_pct    | real       | 0–100（順位）          |
| rs_short_z     | real       | z-score            |
| delta_rs_short | real       | 前日差                |
| vol_z          | real       | 出来高z               |
| calc_run_id    | text       | 実行ID               |
| flags          | text       | `missing_history`等 |

* * *

#### G) `runs`（実行管理：監査と復旧）

| カラム         | 型         | 説明                       |
| ----------- | --------- | ------------------------ |
| calc_run_id | text (PK) | `YYYYMMDD_HHMMSS`等       |
| started_at  | datetime  |                          |
| ended_at    | datetime  |                          |
| status      | text      | `success/failed/partial` |
| snapshot_id | text      | JPX月次                    |
| git_sha     | text      | Actions等で有用              |
| notes       | text      | エラー要約                    |

* * *

### 1.2 成果物メタ（推奨：JSON manifest）

DBとは別に、Driveに置く。

`run_manifest.json`

* run_id

* 作成日時

* 使用snapshot_id

* 対象ユニバース

* 行数（各シート）

* 欠損銘柄数

* pending件数

* 主要エラー（あれば）

**目的**

* 課金者が見ても運用が透明

* 自分のデバッグが楽

* * *

2. 日次バッチのジョブ分割（ロバスト運用）

----------------------

「初回バックフィル」と「日次差分」を分ける。  
理由：初回は重く、クラウドのタイムアウトやレート制限で壊れやすい。

* * *

2.1 ジョブ一覧（最小）
-------------

### Job0：`bootstrap_master`（初回 or 月次）

**頻度**

* 初回

* 月1回（JPX更新）

**処理**

1. JPX月次銘柄一覧を取得→保存（snapshot）

2. `listings` を更新（追加/廃止/市場区分）

3. `pending_listings` の昇格判定（JPXに載ったらresolved）

**成果**

* `snapshot_id` を `active` にする

* * *

### Job1：`pending_scan`（日次：軽量）

**頻度**

* 日次（任意で週次でも可）

**処理**

1. MINKABUスクレイプで銘柄集合取得

2. JPX snapshot の銘柄集合と差分

3. 差分を `pending_listings` に upsert

**失敗時**

* pending更新が止まるだけ

* Core生成・指標算出は継続可能（重要）

* * *

### Job2：`daily_ingest`（日次：差分取得）

**頻度**

* 日次

**処理**

1. その日の対象銘柄集合を確定（後述）

2. yfinanceで日足取得

3. `daily_bars` に upsert

**対象銘柄集合（MVP）**

* 原則：`CORE ∪ IPO` に該当し得る銘柄

* 初期は「JPX掲載の普通株」全体でも可（重いなら絞る）

* * *

### Job3：`universe_build`（日次：T-1確定）

**頻度**

* 日次

**処理**

1. `listings` と `daily_bars`（履歴可用性）から

2. `IPO / CORE` を判定

3. `universe_memberships(date=t)` に保存

* * *

### Job4：`indicator_calc`（日次：差分計算）

**頻度**

* 日次

**処理**

1. `universe_memberships(t)` をロード

2. 必要履歴窓が揃うものだけ計算

3. `indicator_values(t)` へ保存

4. 欠損は `flags` に記録

**バックフィル条件**

* 履歴不足銘柄が発生したら  
  `backfill_queue`（DBなしならJSON）に積む

* * *

### Job5：`export_and_publish`（日次）

**頻度**

* 日次

**処理**

1. XLSX生成（Core/IPO/Pending/凡例）

2. CSV生成（全マージ）

3. `run_manifest.json` 生成

4. Driveに staging→latest でアップロード

**失敗時**

* Driveの `latest` を更新しない（前回版が残る）

* * *

2.2 初回バックフィル（別ジョブに分離）
---------------------

### JobBF：`initial_backfill`

**頻度**

* 初回のみ（手動トリガ）

**目的**

* RS_long（252日）を早期に成立させる

* 以降は日次差分で回す

**戦略**

* 全銘柄を一気にやらない

* 例：時価総額上位から順に

* あるいは Core対象候補のみ

**出力**

* `daily_bars` を厚くする

* `first_trade_date` 推定もこの段階で埋める

* * *

3. クラウド実行（MVP推奨：GitHub Actions）

-------------------------------

### 3.1 ワークフロー構成

* `monthly_master.yml`
  
  * Job0

* `daily_batch.yml`
  
  * Job1〜Job5

* `initial_backfill.yml`
  
  * JobBF（手動）

### 3.2 Secrets

* Google Drive API（サービスアカウント or OAuth）

* MINKABU用（必要なら）

* 失敗通知（必要ならメール/Slack）

### 3.3 失敗時の原則

* **“止まっても壊れない”**を最優先

* データ欠損は manifest と flags で可視化

* Driveは staging→latest で整合性維持

* * *

4. MVPとしての「ワンパス」定義（更新）

----------------------

MVPのワンパス完走とは：

1. JPX snapshot が読める

2. Pending差分が取れる（失敗しても可）

3. 日足が取れる

4. Universe membership が確定される

5. 指標が算出される（算出可能分だけ）

6. XLSX/CSV/manifest が生成される

7. Driveに `/paid/YYYY-MM/latest.*` が置かれる

* * *

5. 運用上の隘路（再掲＋追加）

----------------

* **MINKABUの不安定性**：Pendingは補助。落ちてもCoreは回す。

* **初回負荷**：backfillは分割・手動トリガ。

* **Drive整合性**：staging→latest。latestは常に“完成品”のみ。

* **分母固定**：universe_membershipsに日付保存。過去再計算で壊さない。
