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
  - `0`: ゲートとジョブ成功。ADR-005 の補完 worker 完了は意味しない
- `python scripts/storage/monthly_bus_cli.py commit-snapshot`
  - 現行（REST PATCH commit）: `0` 成功、`1` 契約/入力失敗。`2` は未使用
  - ADR-005 原子 RPC 導入後: `0` は snapshot+request RPC 成功（`noop` / `blocked` / `grandfather` の commit を含む）。補完完了は意味しない。`1` は commit 前の不正で snapshot 非 committed。`2` は RPC / R2 / ネットワーク / 予期しない例外で snapshot 非 committed。dispatch 失敗では `2` を使わない（Monthly は worker を dispatch しない）
- `python -m stockradar.jobs.cron_dispatch_watchdog`
  - `1`: `--target` / `--runs-json` / `--tokyo-date` 不正、未知の watchdog cron
  - `2`: Cloudflare Cron 欠走（expected fire − 2min 以降の東京日内 covering `workflow_dispatch` なし）。`--report-only` 時は欠走でも `0`（GHA evaluator step 用）
  - `0`: `ok` / `skip_closed` / `skip_not_first` / `too_early`
- `python -m stockradar.jobs.validate_daily_dispatch_run_date`
  - `1`: `INPUT_RUN_DATE` / `--input-run-date` が不正（未来日、replay 許容の 3 カレンダー月より古い等）
  - `0`: 検証成功（`is_replay=true|false` を stdout / `GITHUB_OUTPUT` に出力）
- `python -m stockradar.jobs.resolve_monthly_release_for_run_date`
  - `1`: `--run-date` 不正、`--tags-file` 欠落、タグ一覧が空、月次タグの選定不能
  - `0`: 成功（`monthly_tag` / `universe_resolution` / `resolution_reason` を stdout と任意で `GITHUB_OUTPUT` に出力）
- ADR-005 poller（`scripts/storage/mnc_dispatch_cli.py` / `monthly_new_core_backfill_dispatch.yml`。local_only until merge）
  - `0`: tick 成功（claim 0 件も 0）
  - `1`: 契約違反
  - `2`: outbox を `failed` に永続化済みの運用失敗
  - `3`: 使わない
- ADR-005 worker（`scripts/storage/mnc_worker_cli.py` / `monthly_new_core_backfill.yml`。local_only until merge）
  - `0`: 当該 invocation の progress と、chunk 終端なら outbox done / 次 pending。request `completed` を意味しない
  - `1`: schema / fingerprint 契約違反。副作用なし
  - `2`: `failed_retryable` 永続化済み
  - `3`: terminal `blocked` 永続化済み

共通の `3` は ADR-005 worker 専用。Monthly coordinator（`run_monthly.py` / `commit-snapshot`）は `3` を使わない。
