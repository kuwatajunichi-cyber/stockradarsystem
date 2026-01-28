Design Doc v0.4 追補
==================

成果物仕様（XLSX/CSV）＋ run_manifest.json スキーマ
---------------------------------------

* * *

1. XLSX仕様（人間用）

--------------

### 1.1 ファイル名（Drive上）

* `/paid/YYYY-MM/latest.xlsx`

* （任意でアーカイブ）`/paid/YYYY-MM/2026-01-27.xlsx`

MVPは `latest.xlsx` のみでも良い（アーカイブは後回し）。

* * *

### 1.2 シート一覧

1. `README`（凡例・注意書き・更新情報）

2. `CORE_TOP`（Core Universe上位N）

3. `IPO_TOP`（IPO Universe上位N）

4. `PENDING`（任意：pending一覧）

5. `CORE_ALL`（任意：全件。重いならMVPは省略しCSVへ逃がす）

MVPの推奨最小：`README + CORE_TOP + IPO_TOP (+ PENDING任意)`

* * *

### 1.3 共通カラム定義（XLSXテーブル）

#### 識別・メタ

* `date`（YYYY-MM-DD、当日の算出日）

* `listing_id`（例：JPX:5253）

* `code`（4桁）

* `ticker`（例：5253.T）

* `name`

* `market`（Prime/Standard/Growth）

* `security_type`（common/…）

* `share_class`（common/classA/…）

* `listing_age_days`（算出日基準）

* `universe_id`（CORE/IPO/PENDING）

#### 価格・流動性（当日）

* `close`

* `volume`

* `turnover_est`（任意：`close*volume`。売買代金の概算）

#### 指標（MVP）

* `rs_long_pct`（0–100、COREのみ。欠損は空欄）

* `rs_short_z`（COREのみ）

* `delta_rs_short`（COREのみ）

* `vol_z`（COREのみ。IPOは空欄 or IPO専用を後日）

#### ステータス

* `flags`（CSVと共通：例 `missing_history;missing_bar`）

* `notes`（任意：例「履歴不足」「取得失敗」）

* * *

### 1.4 シート別仕様

#### A) `CORE_TOP`

* 対象：`universe_id=CORE`

* 行数：上位N（推奨 50）

* 並び順（推奨）：
  
  1. `rs_long_pct` DESC
  
  2. `vol_z` DESC
  
  3. `rs_short_z` DESC

※RSと出来高偏差の両面を自然に上位へ寄せる

* * *

#### B) `IPO_TOP`

MVPでは IPO の指標が薄い前提で、まずは **観測窓**として出す。

* 対象：`universe_id=IPO`

* 行数：上位N（推奨 50）

* 並び順（暫定）：
  
  1. `turnover_est` DESC（もしくは `volume` DESC）
  
  2. `listing_age_days` ASC（若い順）

（IPOの“注目”は、まず売買代金で見る）

* * *

#### C) `PENDING`（任意）

* 対象：pending_listings（JPX未収載）

* カラム：
  
  * `detected_at`
  
  * `code_candidate`
  
  * `name_candidate`
  
  * `minkabu_key`
  
  * `status`（pending/resolved/ignored）
  
  * `reason`

**注意**：ここに出すのは「監視」目的。Core混入はしない。

* * *

#### D) `README`

**MVPで必ず入れる**（信用・説明・運用透明性の核）

内容（セル配置自由、以下を必須項目として記載）：

* `Generated at`（JST）

* `calc_run_id`

* `JPX snapshot_id`（例：JPX_2026-01）

* `Data sources`（JPX/MINKABU/yfinance）

* `Universe definitions`
  
  * CORE / IPO / PENDING の定義
  
  * IPO threshold（例：120営業日）

* `Missing/Partial policy`
  
  * 欠損日は前回版が残る
  
  * 指標欠損の扱い（空欄＋flags）

* `Field definitions`
  
  * rs_long_pct / rs_short_z / vol_z の意味（簡潔）

* * *

### 1.5 「上位N」vs「全件」の方針（MVP推奨）

* XLSX：**上位Nのみ**

* 全件：**merged CSV**に一本化

理由：

* XLSXが重くならない

* ユーザーの閲覧行動が明確になる

* 将来Web化しやすい

* * *

2. CSV仕様（分析用：全マージ）

------------------

### 2.1 ファイル名

* `/paid/YYYY-MM/latest.csv`

### 2.2 粒度

* 1行 = `date × listing_id × universe_id`

### 2.3 カラム（最小）

`date,listing_id,universe_id,code,ticker,name,market,security_type,share_class,listing_age_days,close,volume,turnover_est,rs_long_pct,rs_short_z,delta_rs_short,vol_z,flags,calc_run_id`

### 2.4 欠損表現ルール（重要）

* 数値欠損：空欄（NULL）

* その理由は `flags` に集約
  
  * `missing_bar`（日足欠損）
  
  * `missing_history`（履歴不足）
  
  * `excluded_low_liquidity`
  
  * `excluded_share_class`
  
  * `pending_not_in_jpx`
  
  * `calc_error`  
    など

* * *

3. run_manifest.json 仕様（監査・透明性）

-------------------------------

### 3.1 目的

* 「今日の成果物が何に基づき、どこまで計算できたか」を機械可読で残す

* 自分のデバッグと、将来の自動通知・運用レポートに使える

### 3.2 配置

* `/paid/YYYY-MM/run_manifest.json`（latestと同階層）

* もしくは `/paid/YYYY-MM/manifests/{calc_run_id}.json`（任意）

MVPは `run_manifest.json` を `latest.*` と同じく上書きでOK。

### 3.3 スキーマ（提案）

`{   "calc_run_id": "20260127_153000",   "generated_at_jst": "2026-01-27T15:32:10+09:00",   "status": "success",   "git_sha": "abc1234",   "inputs": {     "jpx_snapshot_id": "JPX_2026-01",     "minkabu_scan": {       "status": "success",       "detected_pending_count": 3     },     "market_data": {       "source": "yfinance",       "trading_date": "2026-01-27",       "bars_ingested_count": 3900,       "bars_missing_count": 12     }   },   "universes": {     "CORE": {       "members_count": 2800,       "rs_long_computable": 2500,       "rs_short_computable": 2700,       "vol_z_computable": 2750     },     "IPO": {       "members_count": 120     },     "PENDING": {       "members_count": 3     }   },   "outputs": {     "drive": {       "folder": "/paid/2026-01/",       "files": [         {"name": "latest.xlsx", "sha256": "...", "bytes": 1234567},         {"name": "latest.csv", "sha256": "...", "bytes": 2345678},         {"name": "run_manifest.json", "sha256": "...", "bytes": 3456}       ],       "publish_mode": "staging_to_latest"     }   },   "warnings": [     "minkabu_scan_skipped: rate_limited"   ],   "errors": [] }`

### 3.4 運用ルール

* `status` は `success/partial/failed`

* `partial` の定義例：
  
  * market_data欠損が閾値超
  
  * 指標算出が一部ユニバースで未完

* `failed` の場合：
  
  * Driveの `latest.*` を更新しない
  
  * manifestも更新しない（前回成功版が残る）

* * *

4. XLSX/CSV生成時の注意（ロバストネス）

-------------------------

### 4.1 staging→latest（再掲）

* 生成後に `/_staging/` へアップロード

* すべて成功したら
  
  * `latest.xlsx` を置換
  
  * `latest.csv` を置換
  
  * `run_manifest.json` を置換

### 4.2 run_idの一貫性

* XLSX/CSV/manifest の `calc_run_id` は同一

* CSVは `calc_run_id` 列を持つ

* * *

5. MVP実装の優先順位（成果物周り）

--------------------

1. CSV全マージ（縦持ち）を確実に作る

2. XLSXは「上位N＋README」だけ作る

3. manifestを出す（自分の運用が楽になる）
