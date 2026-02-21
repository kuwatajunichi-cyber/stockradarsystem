# 日次レポート スプレッドシート生成 (Render Sheet)

## 概要

Google Drive 上の CSV を読み込み、ローカル XLSX テンプレート（openpyxl）に流し込んで日次レポートを生成する。GCP の Sheets API に依存せず、Drive API のみ使用。

- **ワークフロー**: `.github/workflows/render_sheet.yml`
- **スクリプト**: `scripts/render_sheet/render_sheet.py`
- **設定**: `config/render_sheet.yaml`
- **テンプレート**: `config/templates/indicators_template_v1.0.xlsx`（リポジトリに配置）

## 認証（OAuth）

smoketest と同一の OAuth 認証を使用。**Drive API のみ**（Sheets API 不要）。

- `GDRIVE_OAUTH_CLIENT_ID`
- `GDRIVE_OAUTH_CLIENT_SECRET`
- `GDRIVE_OAUTH_REFRESH_TOKEN`

## 使い方

### 単独テスト（workflow_dispatch）

1. Actions → "Render Sheet (Daily Report)" を選択
2. "Run workflow" をクリック
3. `csv_drive_file_id` に CSV の Drive ファイル ID または共有リンクを入力
4. 必要に応じて他入力も指定

### 本番（日次ワークフロー連携）

daily.yml の最後で、0011_work にアップロードした CSV の file_id を渡して render_sheet を呼び出し、出力を 0012_paid/YYYY-MM/ に保存する。

- `output_folder_id`: 1sUA-HL04eOo9fCBa5fN1OxKRs0Sp-Wf5（0012_paid）
- `run_date` から YYYY-MM フォルダを自動作成
