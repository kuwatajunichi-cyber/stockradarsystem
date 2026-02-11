# Stock Radar System

## Document
https://raw.githubusercontent.com/kuwatajunichi-cyber/stockradarsystem/refs/heads/main/docs/INDEX.md

## 概要

Stock Radar System は、日本株市場を対象に、相対的に注目度が急浮上している銘柄群を
定量指標にもとづいて日次で抽出・可視化するデータパイプライン型システム。

本システムは投資判断や売買シグナルの提示ではなく、「調査対象候補の抽出」に特化する。
成果物は XLSX / CSV として出力し、UI はスプレッドシート操作に委譲する。

> This repository contains research and experimental code for market analysis.
> It does not provide investment advice.

---

## 重要事項（データ取得・利用ポリシー）

- 本リポジトリは研究・検証目的のコードおよび設計を含む。
- データ取得は、各データ提供元の利用規約・robots.txt・レート制限等を順守すること。
- 本システムは、取得元の生データ（例：生のOHLCV等）を再配布しない設計とする。
- データ取得手段は差し替え可能な構造とし、特定提供元への恒久依存を前提としない。
- 本リポジトリに含まれるコードおよび設計は、特定のデータ提供元や取得手段の継続的利用を保証しない。
- 実行環境における具体的なデータ取得設定（頻度・接続方法・認証情報等）は、本リポジトリの管理外とする。


---

## 対象市場・前提

- 対象市場：日本株（JPX上場銘柄）
- 時系列単位：日次
- 実行方式：バッチ処理（定時）
- 実行環境：クラウド（GitHub Actionsを想定）
- ローカルPC常時稼働は不要

---

## 全体構成（論理）
- データソースの具体名は設計上の本質ではないため、本READMEでは抽象化して記述する。

[銘柄マスター/補助情報] + [市場データ] -> [ユニバース生成] -> [指標算出]
|
v
[XLSX/CSV/manifest生成] -> [Drive格納]

yaml
コードをコピーする

---

## ユニバース設計

### 銘柄集合の統合方針
- 正式な分母は「公式ソース由来の月次スナップショット」を基準とする。
- 補助ソースで検出されたが正式分母に未反映の銘柄は、監視レーン（Pending）に隔離する。

### ユニバース区分
- 正式ユニバース：月次スナップショットに含まれる銘柄（指標算出の正規対象）
- IPOユニバース：上場日数が閾値未満の銘柄（別枠で提示）
- Pendingユニバース：補助ソースに存在するが月次スナップショットに存在しない銘柄（監視のみ）

---

## 指標（概要）

- Relative Strength（RS）
  - RSI（オシレーター）とは異なる概念の相対強度。
  - 市場全体に対する相対パフォーマンスを順位/スコアとして提示する。
- 出来高偏差
  - 銘柄固有の出来高分布に対する偏差を計算し、参加者急増の兆候を補助軸として提示する。

※ 指標は合成スコア化も可能だが、MVPでは個別指標を並列提示する。

---

## 成果物仕様（MVP）

### XLSX（閲覧・操作向け）
- Excel / LibreOffice 互換を重視
- 各指標列はソート・フィルタ可能
- 指標の「ひとこと説明」を列名直下の説明行として付記
- 先頭行・先頭列はラベルセル（濃紺背景＋白文字）
- staging -> latest の二段階コミット（中途半端な成果物を露出しない）

### CSV（分析用途）
- 日付 × 銘柄 × ユニバースの縦持ち
- 欠損は空欄、理由は flags に集約

---

## 実行・運用方針

- 「止まらない」より「壊れない」を優先
- 欠損や取得失敗は flags / manifest で可視化
- 成果物は staging -> latest の原子更新
- 実行ID（run_id）とログを保存

---

## スコープ外（明示）

- 投資助言・推奨
- 個別銘柄の定性評価
- Web UI / ダッシュボード（将来検討）

---

## ローカル実行手順（Windows）

以下は Windows（PowerShell）で JPX 銘柄一覧取得ジョブを動かす最小手順です。

### 1. 仮想環境の作成と有効化

```powershell
cd C:\path\to\stockradarsystem
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 依存のインストール

```powershell
pip install -r requirements.txt
```

### 3. 環境変数（任意）

- **JPX_LIST_URL_OVERRIDE**  
  銘柄一覧 Excel の URL を**手動で固定**する場合に指定。指定時は**絶対優先**で、ページからの取得・キャッシュは行いません。
  ```powershell
  $env:JPX_LIST_URL_OVERRIDE = "https://（.xls または .xlsx の直リンク）"
  ```
- **JPX_PAGE_URL**  
  最新URLを抽出する対象ページ。未設定時は既定の銘柄一覧ページ（01.html）を使用します。

### 4. URL の決定とキャッシュ（挙動）

銘柄一覧の URL は**月次で変わる**ため、毎回「最新URLの解決」を試み、失敗時はキャッシュで続行します。

1. **JPX_LIST_URL_OVERRIDE が設定されている**  
   → その URL をそのまま使用（キャッシュは参照・更新しない）。
2. **上記以外**  
   → `resolve_and_update_cache` を実行:
   - **成功**: 固定ページ（JPX_PAGE_URL）から .xls/.xlsx リンクを抽出し、`data/cache/jpx_latest_url.txt` を更新してその URL を採用。
   - **失敗かつキャッシュあり**: キャッシュの URL を採用し、更新失敗理由を **WARN** で出力。ダウンロードは止めない。
   - **失敗かつキャッシュなし**: エラー終了（事前にキャッシュを作成するか、OVERRIDE を設定する必要あり）。

ダウンロード／変換ジョブは「URL が決まった後」だけを担当するため、**URL 更新の失敗だけではダウンロードは止まりません**（キャッシュがあれば続行）。

### 5. ジョブの実行

プロジェクトルートをカレントにし、`src` を PYTHONPATH に含めて実行します。

**銘柄一覧のダウンロード＋CSV 出力（URL 解決を含む）:**

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.fetch_jpx_list
```

**URL 更新のみ（独立ジョブ。キャッシュの更新だけ行い、ダウンロードはしない）:**

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.update_jpx_url_cache
```
（`update_jpx_url_cache` の成功時は採用した URL を標準出力に出力。失敗時はキャッシュがあれば WARN のうえその URL を出力、キャッシュが無ければエラーで終了。）

**fetch_jpx_list の結果:**

- 成功時: `data/raw/jpx/jpx_list_YYYYMMDD.xls` または `.xlsx` と `data/processed/jpx/jpx_list_YYYYMMDD.csv`（UTF-8 BOM）が出力されます。
- 失敗時: エラーメッセージを表示し、終了コード 1 で終了します（例: 最新URL取得失敗かつキャッシュなし、HTTP エラー、保存失敗、**ダウンロード結果がExcel形式でない**）。

### 検証・トラブルシュート

- **「CSVの出力に失敗」「Excelの読み込みに失敗」など**  
  実際の原因（例外名・メッセージ）を確認するには、既存の .xls / .xlsx を使って読み込み〜CSV書き込みを試す検証スクリプトを実行してください。  
  ```powershell
  python scripts/verify_jpx_xlsx_to_csv.py
  # または対象ファイルを指定: python scripts/verify_jpx_xlsx_to_csv.py "data/raw/jpx/jpx_list_20260207.xls"
  ```
- **「ダウンロード結果がExcel形式ではありません（HTML/XMLの可能性）」**  
  採用した URL が HTML 等になっています。JPX_LIST_URL_OVERRIDE で Excel の**直リンク**を指定するか、キャッシュを正しい URL で更新してください。
- **「最新URLの取得に失敗し、キャッシュもありません」**  
  まず `python -m stockradar.jobs.update_jpx_url_cache` をネットワークが通る状態で実行するか、JPX_LIST_URL_OVERRIDE で URL を固定してください。

---

## 一次ユニバース生成（JPX銘柄一覧ベース）

JPX の processed CSV（例: `data/processed/jpx/jpx_list_YYYYMMDD.csv`）から、\n市場・商品区分に基づく一次ユニバース（universe_primary）を構築します。

- **一次ユニバース区分（universe_primary）**  
  - `equity_domestic`：内国株式  
  - `equity_foreign`：外国株式  
  - `etf_etn`：ETF・ETN  
  - `reit_funds`：REIT・ベンチャーファンド・カントリーファンド・インフラファンド  
  - `pro_market`：PRO Market  
  - `investment_securities`：出資証券  
  - `unknown`：上記に分類不能

### 入力CSVの想定列（最低限）

- `コード`  
- `銘柄名`  
- `市場・商品区分`  
  - 無い場合でもジョブは継続し、全件 `unknown` にフォールバック（UNIVERSE_SCHEMA アラートを出力）。

### 出力

- **マスター**  
  - `data/universe/jpx/universe_master_YYYYMMDD.csv`  
  - columns: `date`, `code`, `name`, `market_product_raw`, `universe_primary`  
  - `code` は 4桁文字列（ゼロ埋め維持）
- **ユニバースごとの銘柄集合**  
  - `data/universe/jpx/sets_YYYYMMDD/{universe_id}.csv`  
  - 1列: `code`（ヘッダ付き）  
  - `universe_id` は上記 7種（空集合でもヘッダのみのCSVとして出力）

### スキーマ破壊アラート（UNIVERSE_SCHEMA）

- **Trigger A: 「市場・商品区分」列が存在しない**  
  - `ALERT[UNIVERSE_SCHEMA]: COLUMN_MISSING market_product`  
  - 全銘柄を `unknown` に分類して出力（ジョブは成功扱い）。
- **Trigger B: 「市場・商品区分」のカテゴリ集合が前回基準から変化**  
  - 基準: `data/cache/jpx_market_product_categories.json`  
  - 差分 added/removed を明示して  
    - `ALERT[UNIVERSE_SCHEMA]: CATEGORY_SET_CHANGED added=[...] removed=[...]`  
  - 成功時のみキャッシュを更新（初回は「基準作成」として保存）。
- **コード・銘柄名の欠損**  
  - 欠損があってもジョブは継続し、空文字として出力する。  
  - 件数は `WARN[UNIVERSE_SCHEMA]: CODE_MISSING ...` / `WARN[UNIVERSE_SCHEMA]: NAME_MISSING ...` として出力。

### 実行方法

PowerShell 例（プロジェクトルートにて）:

```powershell
$env:PYTHONPATH = "src"

# 入力CSVを明示する場合
python -m stockradar.jobs.build_universe_from_jpx --input data/processed/jpx/jpx_list_YYYYMMDD.csv

# --input を省略すると data/processed/jpx/jpx_list_*.csv のうち
# ファイル名順で最新のものを自動選択
python -m stockradar.jobs.build_universe_from_jpx
```

実行後:

- UNIVERSE_SCHEMA に関する ALERT/WARN は標準エラーに出力されますが、  
  いずれもダウンロード等の他ジョブには影響しません（処理は継続し `unknown` へフォールバック）。  
- `data/universe/jpx/` 以下にマスターと 7種のユニバース集合が出力されます。

---

## 二次ユニバース（equity_domestic の ipo / illiquid / core 分割）

一次ユニバースの `equity_domestic` を、yfinance の日次データ（Close, Volume）を用いて  
**ipo**（上場日数不足・取得失敗寄せ）／**illiquid**（売買代金近似の中央値が閾値未満）／**core**（残差）に排他分割します。  
取得ジョブと分類ジョブは**独立**しており、取得失敗があっても分類ジョブは「ipo 寄せ」で継続できます。

### 環境変数（例）

| 変数 | 説明 | 既定値 |
|------|------|--------|
| IPO_LOOKBACK_DAYS | IPO判定に必要な営業日数 | 252 |
| LIQ_LOOKBACK_DAYS | 流動性判定の直近営業日数 | 60 |
| LIQ_MIN_MEDIAN_TURNOVER_YEN | 中央値がこれ未満なら illiquid（**必須**） | なし |
| YF_BATCH_SIZE | 取得バッチサイズ | 100 |
| YF_SLEEP_SEC_BETWEEN_BATCHES | バッチ間スリープ秒 | 5 |
| YF_RETRY_MAX | 銘柄あたり最大再試行回数 | 3 |
| YF_RETRY_BACKOFF_SEC | 再試行待機秒（カンマ区切り） | 5,15,30 |

### ジョブ A: yfinance 日次取得（fetch_yf_daily_for_universe）

- **入力**: `equity_domestic.csv`（`--input` で指定。未指定時は `data/universe/jpx/sets_YYYYMMDD/equity_domestic.csv` の最新を自動選択）
- **required_days**: `max(IPO_LOOKBACK_DAYS, LIQ_LOOKBACK_DAYS)` 分のデータを取得
- **キャッシュ**: `data/cache/yf_daily/{code}.csv`（Close, Volume、日付 index）
- **manifest**: `data/cache/yf_daily/_manifest.jsonl`（code, requested_days, fetched_bars, status, error, fetched_at）
- **途中再開**: manifest で `status=ok` かつ `fetched_bars >= required_days` の銘柄はスキップ。`--force` で全件再取得。

```powershell
$env:PYTHONPATH = "src"
$env:LIQ_MIN_MEDIAN_TURNOVER_YEN = "10000000"   # 分類ジョブ用（取得ジョブでは不要）

python -m stockradar.jobs.fetch_yf_daily_for_universe --input data/universe/jpx/sets_20260207/equity_domestic.csv
# または入力省略で最新 sets_* から自動選択
python -m stockradar.jobs.fetch_yf_daily_for_universe
# 全件再取得
python -m stockradar.jobs.fetch_yf_daily_for_universe --force
```

### ジョブ B: 二次分割（split_equity_domestic_secondary）

- **入力**: `equity_domestic.csv` と `data/cache/yf_daily/`（キャッシュ＋manifest）
- **出力**: `data/universe/jpx/sets_secondary_YYYYMMDD/`
  - `equity_domestic_ipo.csv`, `equity_domestic_illiquid.csv`, `equity_domestic_core.csv`（いずれも `code` 1列・ヘッダ付き）
  - 上記に銘柄名列を加えた `*_with_name.csv`（`code`, `name`）。銘柄名のマスタは JPX processed CSV（`data/processed/jpx/jpx_list_YYYYMMDD.csv`）。該当 CSV が無い場合は銘柄名付きは出力しない。
- **ログサマリ**: 対象銘柄数、取得ok/失敗/bars不足、ipo/illiquid/core 件数、illiquid 閾値・期間を標準エラーに出力。

```powershell
$env:PYTHONPATH = "src"
$env:LIQ_MIN_MEDIAN_TURNOVER_YEN = "10000000"   # 必須

python -m stockradar.jobs.split_equity_domestic_secondary --input data/universe/jpx/sets_20260207/equity_domestic.csv
# または入力省略で最新 sets_* から自動選択
python -m stockradar.jobs.split_equity_domestic_secondary
```

### 実行順序

1. 一次ユニバース生成で `sets_YYYYMMDD/equity_domestic.csv` を用意する。
2. **ジョブ A** で yfinance を取得（キャッシュ・manifest ができる）。**必ずプロジェクトルートをカレントにして実行**すること（キャッシュパスの一貫性のため）。
3. **ジョブ B** で ipo / illiquid / core に分割（同じくプロジェクトルートで実行。`LIQ_MIN_MEDIAN_TURNOVER_YEN` を設定してから実行）。

**「全件取得失敗」になる場合**: ジョブ B は `data/cache/yf_daily/_manifest.jsonl` を参照します。manifest が無い（ジョブ A をまだ実行していない、または別ディレクトリで実行した）場合は全銘柄が ipo に分類されます。先にジョブ A をプロジェクトルートで実行し、取得が完了してからジョブ B を実行してください。ジョブ A では `period` で空になる場合に `start/end` で再試行するフォールバックを入れています。

---

## 日次指標算出（equity_domestic_core 対象）

月次で生成済みの `equity_domestic_core_with_name.csv` を対象に、日次で指標（出来高zscore/RS）を算出します。

### 環境変数

| 変数 | 説明 | 既定値 |
|------|------|--------|
| Z_LOOKBACK_DAYS | 出来高zscoreの窓サイズ（営業日数） | 60 |
| RS_WINDOWS | RS算出の期間リスト（営業日数、カンマ区切り） | 63,126,252 |
| RS_BENCHMARK | RS算出のベンチマーク（TOPIX/NIKKEI/BOTH） | BOTH |
| RS_WEIGHTS | RS合成用の重みリスト（カンマ区切り、任意） | なし |
| BUFFER_DAYS | キャッシュ取得時のバッファ日数 | 20 |
| YF_BATCH_SIZE | 取得バッチサイズ | 100 |
| YF_SLEEP_SEC_BETWEEN_BATCHES | バッチ間スリープ秒 | 5 |
| YF_RETRY_MAX | 銘柄あたり最大再試行回数 | 3 |
| YF_RETRY_BACKOFF_SEC | 再試行待機秒（カンマ区切り） | 5,15,30 |

### ジョブ構成

#### Job1: resolve_trading_day
- Asia/Tokyo基準で run_date を決定
- 東証営業日（XTKS）か判定
- 休場なら以降ジョブをスキップ（success扱い）

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.resolve_trading_day
# または特定日を指定
python -m stockradar.jobs.resolve_trading_day --date 2026-02-11
```

#### Job2: ensure_index_cache
- ベンチETFのキャッシュ確保（BOTHが標準）
  - TOPIX proxy: 1306.T
  - Nikkei225 proxy: 1321.T
- 不足時のみ重い取得、通常は差分取得

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.ensure_index_cache --run-date 2026-02-11
```

#### Job3: ensure_core_cache
- 入力: `equity_domestic_core_with_name.csv`（最新 sets_secondary_YYYYMMDD から自動選択）
- 各銘柄のOHLCVキャッシュを確保（不足時のみ重い取得）
- 分割取得 + インターバル + リトライ + 途中再開（manifest）

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.ensure_core_cache --run-date 2026-02-11
# または入力ファイルを明示
python -m stockradar.jobs.ensure_core_cache --input data/universe/jpx/sets_secondary_20260211/equity_domestic_core_with_name.csv --run-date 2026-02-11
```

#### Job4: compute_indicators_for_core
- 入力: `equity_domestic_core_with_name.csv`、`data/cache/yf_daily/`、`data/cache/yf_index/`
- 出力: `data/indicators/daily/indicators_YYYYMMDD.csv`
- 指標:
  - 出来高zscore（売買代金近似ベース）
  - RS（B方式：期間リターン差）

```powershell
$env:PYTHONPATH = "src"
python -m stockradar.jobs.compute_indicators_for_core --run-date 2026-02-11
# または入力ファイルを明示
python -m stockradar.jobs.compute_indicators_for_core --input data/universe/jpx/sets_secondary_20260211/equity_domestic_core_with_name.csv --run-date 2026-02-11
```

### 出力ファイル

- **内部キャッシュ（非配布）**
  - `data/cache/yf_daily/{code}.csv`（銘柄別OHLCV、最低Close/Volume）
  - `data/cache/yf_index/{bench}.csv`（ベンチETF）
- **日次指標（分析用・配布前の生）**
  - `data/indicators/daily/indicators_YYYYMMDD.csv`（縦持ち：date, code, indicators...）
    - 列例: `date`, `code`, `name`（任意）, `turnover_yen`, `z_turnover_{Z_LOOKBACK_DAYS}`, `rs63_topix`, `rs126_topix`, `rs252_topix`, `rs63_nikkei`, `rs126_nikkei`, `rs252_nikkei`, `n_bars_used`

### GitHub Actions での実行

`.github/workflows/daily.yml` が毎営業日 16:00 JST 以降に自動実行されます。

- schedule: 毎営業日 16:00 JST 以降（当日バー反映後）
- concurrency: 同一workflowの多重起動禁止
- fetch系は部分成功を許容しつつmanifestに残す
- computeで対象銘柄の有効計算率が極端に低い場合はfail

### ローカル実行例（全ジョブ順次実行）

```powershell
$env:PYTHONPATH = "src"
$RUN_DATE = "2026-02-11"

# Job1: 営業日判定
python -m stockradar.jobs.resolve_trading_day --date $RUN_DATE

# Job2: ベンチマークキャッシュ確保
python -m stockradar.jobs.ensure_index_cache --run-date $RUN_DATE

# Job3: 銘柄キャッシュ確保
python -m stockradar.jobs.ensure_core_cache --run-date $RUN_DATE

# Job4: 指標算出
python -m stockradar.jobs.compute_indicators_for_core --run-date $RUN_DATE
```
