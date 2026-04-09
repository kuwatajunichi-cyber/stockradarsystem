# Quality Gate Scope Lock

Gate 0 時点での対象凍結リスト:

- `src/stockradar/indicators/date_anchor.py`
- `src/stockradar/indicators/rs.py`
- `src/stockradar/indicators/risk_adjusted.py`
- `src/stockradar/indicators/zscore.py`
- `src/stockradar/jobs/compute_indicators_for_core.py`
- `src/stockradar/jobs/ensure_index_cache.py`
- `src/stockradar/jobs/ensure_core_cache.py`
- `scripts/run_monthly.py`
- `tests/`
- `.github/workflows/test.yml`
- `.github/workflows/daily.yml`
- `.github/workflows/monthly.yml`
- `pyproject.toml`

例外ルール:

- 品質ゲート成立に必須な文書追加（`docs/contracts/*`, `tests/TEST_RELOCATION_MAP.md`, workflow 説明文書）は許可。
- それ以外の新規変更は明示承認が必要。
