"""Contract: ADR-005 MNC poller/worker workflows."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]


def test_poller_uses_gh_dispatch_token_not_github_token() -> None:
    text = (
        _REPO / ".github" / "workflows" / "monthly_new_core_backfill_dispatch.yml"
    ).read_text(encoding="utf-8")
    assert "GH_DISPATCH_TOKEN" in text
    assert "secrets.GITHUB_TOKEN" not in text
    assert "contents: read" in text
    assert "actions: write" not in text
    loaded = yaml.safe_load(text)
    assert loaded["permissions"] == {"contents": "read"}


def test_worker_concurrency_and_timeout() -> None:
    text = (_REPO / ".github" / "workflows" / "monthly_new_core_backfill.yml").read_text(
        encoding="utf-8"
    )
    assert 'group: mnc-${{ inputs.request_id }}' in text
    assert "timeout-minutes: 120" in text
    assert "actions: write" not in text
    assert "secrets.GITHUB_TOKEN" not in text


def test_worker_passes_r2_base_prefix_like_daily() -> None:
    """MNC must write under the same physical prefix Daily reads (NoSuchKey otherwise)."""
    text = (_REPO / ".github" / "workflows" / "monthly_new_core_backfill.yml").read_text(
        encoding="utf-8"
    )
    assert "secrets.R2_BASE_PREFIX" in text
    assert "secrets.R2_ENDPOINT_URL" in text
    assert "secrets.R2_BUCKET" in text
    assert "secrets.R2_ACCOUNT_ID" in text


def test_monthly_inline_series_seed_job_contract() -> None:
    """Steady-state seed runs inside monthly.yml (Daily write_derived pattern)."""
    text = (_REPO / ".github" / "workflows" / "monthly.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    jobs = loaded["jobs"]
    assert "series_seed" in jobs
    seed = jobs["series_seed"]
    assert seed["needs"] == ["build"]
    assert "mnc_outcome == 'runnable'" in str(seed.get("if") or "")
    assert seed.get("timeout-minutes") == 180
    assert seed["permissions"] == {"contents": "read"}
    assert "actions: write" not in text
    seed_run = "\n".join(
        str(step.get("run") or "") for step in seed.get("steps") or []
    )
    assert "mnc_worker_cli.py drain-request" in seed_run
    assert "secrets.R2_BASE_PREFIX" in text
    assert "MNC_CODE_CONCURRENCY" in text
    build = jobs["build"]
    assert "mnc_request_id" in (build.get("outputs") or {})
    assert "mnc_outcome" in (build.get("outputs") or {})
    finalize = jobs["finalize_run"]
    assert "series_seed" in finalize["needs"]
    assert "SEED_RESULT" in "\n".join(
        str(step.get("run") or "") for step in finalize.get("steps") or []
    )


def test_mnc_dispatch_cli_requires_gh_dispatch_token() -> None:
    text = (_REPO / "scripts" / "storage" / "mnc_dispatch_cli.py").read_text(encoding="utf-8")
    assert "GH_DISPATCH_TOKEN" in text
    assert "GITHUB_TOKEN forbidden" in text
