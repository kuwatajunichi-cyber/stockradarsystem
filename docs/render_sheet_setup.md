# 日次レポート スプレッドシート生成 (Render Sheet)

## 概要

Google Drive 上の CSV を読み込み、スプレッドシートテンプレに流し込んで日次レポートを生成する。

- **ワークフロー**: `.github/workflows/render_sheet.yml`
- **スクリプト**: `scripts/render_sheet/render_sheet.py`
- **設定**: `config/render_sheet.yaml`

## 認証（OAuth）

smoketest と同一の OAuth 認証を使用。以下の Secrets が設定済みであること:

- `GDRIVE_OAUTH_CLIENT_ID`
- `GDRIVE_OAUTH_CLIENT_SECRET`
- `GDRIVE_OAUTH_REFRESH_TOKEN`

※ Sheets API を使うため、refresh token 取得時に **Drive** と **Sheets** の両方のスコープを付与すること。既存の token が Drive のみの場合は、再認証が必要。詳細は `docs/トラブルシューティング_GD編.md` 参照。

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
