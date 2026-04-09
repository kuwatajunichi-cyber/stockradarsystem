# TEST RELOCATION MAP

品質ゲート再編の対応表:

- `tests/unit/`
  - `tests/unit/test_indicator_normalization_audit.py`（正規化責務の監査）
- `tests/job_integration/`
  - `tests/job_integration/test_compute_indicators_parallel_equivalence.py`
  - `tests/job_integration/test_rerun_idempotency_contract.py`
- `tests/smoke/`
  - `tests/smoke/test_exit_code_contracts.py`

既存の `tests/*.py` は後方互換のため暫定残置し、新規契約テストは marker ベースの新階層で管理する。
