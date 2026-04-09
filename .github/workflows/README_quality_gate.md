# Reusable Quality Gate

`reusable_quality_gate.yml` は運用workflow向けの共通 preflight。

## Inputs

- `python-version` (default: `3.11`)

## 実行内容

- `ruff check src tests scripts`
- `mypy src/stockradar/jobs src/stockradar/indicators`
- `pytest --strict-markers -m "unit"`
- `pytest --strict-markers -m "job_integration"`
- `pytest --strict-markers -m "smoke"`
- `actionlint`

## Fail 条件

- いずれかの検査が失敗した場合、呼び出し元 workflow は `needs: preflight` により本体ジョブを起動しない。
