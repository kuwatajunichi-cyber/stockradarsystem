"""Contract: P0 security smoke script structure (Secrets-free)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SECURITY_SMOKE = _REPO / "scripts" / "smoke" / "supabase_control_plane_security_smoke.py"
_WORKFLOW = _REPO / ".github" / "workflows" / "supabase_security_smoketest.yml"


def test_security_smoke_fixed_anon_control_endpoint() -> None:
    text = _SECURITY_SMOKE.read_text(encoding="utf-8")
    assert 'AUTH_HEALTH_PATH = "/auth/v1/health"' in text
    assert "SUPABASE_PUBLISHABLE_KEY" in text
    assert "invalid-publishable-key-for-p0-smoke" in text
    assert 'POSTGREST_INSUFFICIENT_PRIVILEGE = "42501"' in text
    assert "commit_jpx_url_cache" in text
    assert "_COMMIT_FIXED_CACHE_BODY" in text
    assert "sb_publishable_" in text


def test_security_smoke_does_not_use_service_role_key() -> None:
    text = _SECURITY_SMOKE.read_text(encoding="utf-8")
    assert "SUPABASE_SECRET_KEY" not in text


def test_security_smoke_workflow_manual_dispatch_only() -> None:
    wf = _WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in wf
    assert "SUPABASE_PUBLISHABLE_KEY" in wf
    assert "supabase_control_plane_security_smoke.py" in wf
