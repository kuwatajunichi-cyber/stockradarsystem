# Exit Code Contract

以下のエントリポイントは終了コード契約を共有する。

- `1`: 入力不備、契約違反（必須入力不足・成果物契約不一致など）
- `2`: 実行時失敗（依存ジョブ失敗、外部I/O失敗、予期しない例外）

## 対象エントリポイント

- `python -m stockradar.jobs.compute_indicators_for_core`
  - `1`: 不正な `--run-date`、入力CSV不備、結果0件など
  - `2`: stale OHLC 残存、ベンチ stale 残存など実行時停止
- `python -m stockradar.jobs.ensure_index_cache`
  - `1`: 不正な `--run-date`、全件失敗
  - `2`: `run_date` 指定時 stale 残存
- `python -m stockradar.jobs.ensure_core_cache`
  - `1`: 不正な `--run-date`、全件失敗
  - `2`: `run_date` 指定時 stale 残存（閾値超過）
- `python scripts/run_monthly.py`
  - `1`: 3CSV欠落、検証ゲート不合格、入力契約違反
  - `2`: ジョブ実行失敗、manifest生成失敗、予期しない例外
