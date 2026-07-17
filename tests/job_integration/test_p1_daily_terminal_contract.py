from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.job_integration


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _daily_yml_text() -> str:
    return (_repo_root() / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")


@pytest.mark.job_integration
def test_daily_yml_does_not_coerce_enrichment_to_skipped() -> None:
    text = _daily_yml_text()
    assert not re.search(
        r'ENRICH_RESULT="\$\{\{ needs\.event_cause_enrichment\.result \}\}"\s*\n\s*if \[ "\$ENRICH_RESULT" != "success" \]',
        text,
    ), "daily.yml must not normalize enrichment failure/cancelled to skipped"


@pytest.mark.job_integration
def test_daily_yml_passes_raw_enrichment_result_to_finalize() -> None:
    text = _daily_yml_text()
    assert '--enrichment-result "$ENRICH_RESULT"' in text or (
        '--enrichment-result "${{ needs.event_cause_enrichment.result }}"' in text
    )
