# Google Drive OAuth（refresh token）トラブルシューティング（あなた用）

1. まず結論（判断フロー）

--------------

ActionsがDrive操作で落ちたら、最初にログから次を判定する。

* **A: `invalid_grant` / `Refresh token expired or revoked` が出ている**  
  → refresh tokenの再取得が必要（本書の「3」へ）

* **B: `insufficientPermissions` / `The user has not granted ...`**  
  → スコープ/認可/共有権限問題（「4」へ）

* **C: それ以外（400/403/404など）**  
  → フォルダID間違い、パス解決、Drive側権限、APIリクエスト不備（「5」へ）

--------------

1. そもそもの仕組み（最低限）

--------------

* `refresh_token` は長命の鍵。これが生きていれば、Actionsは都度 `access_token`（短命）を再発行してDrive APIを叩ける。

* つまり、**普段は何も更新しない**。壊れたときだけ再取得。

--------------

1. 失効・無効化が起きる主な原因（頻度順）

--------------

1. 専用Googleアカウントで「アプリのアクセス権」を手動削除した

2. GCP側の OAuth クライアントを作り直した / client_secretを変えた

3. refresh token取得を何度もやり直して古いtokenが無効化された

4. まれなGoogle側都合（ポリシー/不正検知など）

※「日次で使うこと」自体は失効理由になりにくい。

--------------

1. refresh token再取得（復旧手順）

--------------

## 3-1. 事前に確認するもの

* GCPプロジェクト：Drive APIが有効

* OAuth同意画面：
  
  * External
  
  * **In production**（Testingだと失効が早い可能性がある）

* OAuthクライアント：Desktop app の `client_id` / `client_secret` が手元にある

* ログイン：専用Googleアカウントでブラウザログインできる

## 3-2. 再取得手順（最短）

1. ローカル（Windows）で、以前使った `get_refresh_token.py` を実行

2. ブラウザが開く → 専用Googleアカウントで許可

3. 端末に表示される `refresh_token` をコピー

## 3-3. GitHubへ反映

* GitHub → Repo → Settings → Secrets and variables → Actions

* `GDRIVE_OAUTH_REFRESH_TOKEN` を新しい値で上書き
  
  * クォート不要、改行なし、値ベタ貼り

## 3-4. 動作確認（復旧確認）

* スモークテスト or 日次WFを手動実行

* Driveへの「一覧取得」や「ファイル作成」まで通れば復旧完了

--------------

1. 権限/スコープ系エラーの対処

--------------

### 4-1. `insufficientPermissions`

原因候補：

* スコープが不足（例：`drive.file` だと既存フォルダ操作に不足することがある）

* 認可時にスコープを許可していない

対処：

* 必要スコープを確認（現状の実装が `https://www.googleapis.com/auth/drive` を前提にしているか）

* スコープを変えたなら **再認可→refresh token再取得**が必要

### 4-2. `The user has not granted ...`

* refresh tokenは生きていても、許可範囲が足りない

* 対処は同じく「スコープ見直し→再認可→再取得」

--------------

1. よくある非OAuth原因（見落としやすい）

--------------

### 5-1. 404 / `File not found`

* フォルダIDが誤り

* 対象フォルダが削除/移動された

* 専用アカウントに共有されていない

対処：

* 対象フォルダをブラウザで開けるか確認（専用アカウントで）

* 共有設定を確認（閲覧ではなく編集が必要な場合あり）

### 5-2. 403だけどinvalid_grantではない

* Drive側共有権限が「閲覧者」になっている

* マイドライブ配下共有フォルダの編集権限が不足

対処：

* 該当フォルダの共有権限を「編集者」へ

### 5-3. 429 / rate limit

* 連続呼び出し過多。日次運用程度なら通常はコード側のリトライ/並列が原因。

--------------

1. 重大事故を避けるルール（運用メモ）

--------------

* refresh tokenをむやみに取り直さない（取り直しがトリガで古いtokenが死ぬ場合がある）

* GCPのOAuthクライアントを作り直さない（作り直すならSecrets含め全面更新）

* 専用Googleアカウントの「アプリ連携」を不用意に削除しない

* 失効時に備えて：
  
  * `client_id` / `client_secret` の入ったJSONはローカル安全場所に保管
  
  * `get_refresh_token.py` は `C:\LpcalPy\...` に固定配置（忘却対策）

--------------

1. 記録しておくべき“最低情報”（どこかにメモ）

--------------

* GCPプロジェクト名（またはID）

* OAuthクライアント名（Desktop app のどれか）

* 使っているスコープ（drive / drive.file 等）

* 対象フォルダID（work/paid/public）

--------------

1. 「更新が必要か？」の見極め早見表

--------------

* `invalid_grant` → **ほぼ確実に再取得**

* `insufficientPermissions` → **スコープ/共有権限の見直し**

* `File not found` → **フォルダID or 共有設定**
