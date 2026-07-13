from __future__ import annotations

import pytest

from stockradar.storage.phase4_rollout import (
    monthly_read_allows_github_fallback,
    monthly_read_uses_supabase_primary,
    monthly_write_is_required,
    normalize_phase4_rollout_stage,
    publish_dual_write_enabled,
)


@pytest.mark.unit
def test_normalize_phase4_rollout_stage() -> None:
    assert normalize_phase4_rollout_stage("4b") == "4b"
    with pytest.raises(ValueError):
        normalize_phase4_rollout_stage("3c")


@pytest.mark.unit
@pytest.mark.parametrize("stage,monthly_req,read_sb", [("4a", False, False), ("4b", False, True), ("4c", True, True)])
def test_phase4_rollout_core(stage, monthly_req, read_sb) -> None:
    assert monthly_write_is_required(stage) is monthly_req
    assert monthly_read_uses_supabase_primary(stage) is read_sb
    assert monthly_read_allows_github_fallback(stage) is (stage == "4b")
    assert publish_dual_write_enabled(stage) is (stage in {"4b", "4c"})
