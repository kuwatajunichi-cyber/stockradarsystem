# TEST RELOCATION MAP

品質ゲート再編の対応表:

- `tests/unit/`
  - `tests/unit/test_indicator_normalization_audit.py`（正規化責務の監査）
- `tests/job_integration/`
  - `tests/job_integration/test_compute_indicators_parallel_equivalence.py`
  - `tests/job_integration/test_additional_workflow_contracts.py`
  - `tests/job_integration/test_rerun_idempotency_contract.py`
- `tests/smoke/`
  - `tests/smoke/test_exit_code_contracts.py`

既存の `tests/*.py` は後方互換のため暫定残置し、新規契約テストは marker ベースの新階層で管理する。

マーカー付与済み（ルート暫定置き・CI ゲート対象）の例:

- `unit`: `tests/test_core_csv_selection.py`, `tests/test_monthly_release_pick.py`
- `job_integration`: `tests/test_daily_workflow_contract.py`, `tests/job_integration/test_additional_workflow_contracts.py`, `tests/test_resolve_core_csv.py`
- `smoke`: `tests/test_upload_to_all_targets.py`, `tests/test_render_sheet.py`, `tests/test_compute_indicators_main_smoke.py`

削除: `tests/test_compute_indicators_parallel_contract.py`（`test_compute_indicators_parallel_equivalence` と重複かつ Windows 下で不安定なため）。
