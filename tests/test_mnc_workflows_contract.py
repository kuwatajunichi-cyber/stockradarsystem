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


def test_mnc_dispatch_cli_requires_gh_dispatch_token() -> None:
    text = (_REPO / "scripts" / "storage" / "mnc_dispatch_cli.py").read_text(encoding="utf-8")
    assert "GH_DISPATCH_TOKEN" in text
    assert "GITHUB_TOKEN forbidden" in text
