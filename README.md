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
