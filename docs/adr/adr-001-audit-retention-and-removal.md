# ADR-001: 監査用トレーサビリティ（温存・削除判断の記録）

## 状態

採用（2025-03 合意）

## 文脈

コードベースに未使用・ legacy のシンボルが残っており、将来の監査で「なぜ削除しなかったか」「なぜ残したか」を追跡可能にする必要がある。

## 決定

### 温存（必須）4件

|シンボル|本来用途|残存経緯|再利用条件|再評価タイミング|
|----------|----------|----------|------------|------------------|
|`get_folder_id_public` / `GDRIVE_FOLDER_ID_PUBLIC`|古い顧客向け成果物をサンプルとしてアップロードする先|将来利用予定のため維持|サンプルアップロード機能実装時|12か月後または該当機能実装時|
|`get_rs_weights` / `RS_WEIGHTS`|RS 合成用の重みリスト（環境変数）|未確定仕様の名残。将来の RS 合成仕様再開に備えて維持|RS 合成仕様確定時|12か月後または RS 仕様確定時|
|`FakeDriveAdapter`|テスト用 Drive の Fake 実装|テスト I/O 分離のため必須。削除非推奨|テストで注入する想定|不要（常時温存）|
|`InMemoryCategoryCache`|テスト用カテゴリキャッシュの Fake 実装|テスト I/O 分離のため必須。削除非推奨|テストで注入する想定|不要（常時温存）|

### 削除対象（実施済み）5カテゴリ

|カテゴリ|削除理由|影響範囲|ロールバック方法|
|----------|----------|----------|------------------|
|`SHEETS_SCOPE`|Sheets API 未使用。Drive API のみ利用|`scripts/gdrive/drive_client.py`|git revert で復元|
|`build_sheets_service`|Sheets API 未使用|`scripts/gdrive/drive_client.py`|git revert で復元|
|`find_file_in_folder`|呼び出しなし|`scripts/gdrive/drive_client.py`|git revert で復元|
|`write_manifest_entry`|呼び出しなし。`update_manifest` で代替|`src/stockradar/utils/yf_cache.py`|git revert で復元|
|`compute_candle_labels` 内の未使用ローカル変数（`latest_atr_val` 等）|デッドコード|`src/stockradar/utils/candle_descriptor.py`|git revert で復元|

### 削除再判定条件

以下の **3条件をすべて満たす** 場合にのみ、温存対象の削除を再検討する：

1. **6か月未使用**: 該当シンボルへの参照が 6 か月以上ゼロ
2. **参照ゼロ**: コードベース内に import または直接参照がゼロ
3. **代替実装確定**: 代替手段が実装され、運用で検証済み

## リンク

- 監査修正実行計画: `docs/` 参照
- `docs/INDEX.md` から本 ADR に到達可能
