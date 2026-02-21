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

### 本番（workflow_call）

他のワークフローから呼び出す場合:

```yaml
jobs:
  render_sheet:
    uses: ./.github/workflows/render_sheet.yml
    with:
      csv_drive_file_id: ${{ needs.upload.outputs.csv_file_id }}
    secrets: inherit
```

※ `csv_drive_file_id` は日次ワークフローの CSV アップロード後に取得したファイル ID を渡す。
