"""Shared pytest fixtures (secrets-free CI)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _secrets_free_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent unit/job_integration tests from calling live Supabase."""
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
