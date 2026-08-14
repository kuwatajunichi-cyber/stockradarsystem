"""Contract: Phase 4.5 rollout stage helpers."""
from __future__ import annotations

import pytest

from stockradar.storage.phase4_5_rollout import (
    derived_active_pointer_update_allowed,
    derived_latest_projection_update_allowed,
    derived_shadow_snapshot_write_enabled,
    derived_writer_enabled,
    normalize_phase4_5_rollout_stage,
)

pytestmark = pytest.mark.unit


def test_off_stage_disables_derived_writer() -> None:
    assert derived_writer_enabled("off") is False
    assert derived_shadow_snapshot_write_enabled("off") is False


def test_4_5a_allows_shadow_snapshot_only() -> None:
    assert derived_shadow_snapshot_write_enabled("4.5a") is True
    assert derived_latest_projection_update_allowed("4.5a", "normal") is False
    assert derived_active_pointer_update_allowed("4.5a", "normal") is False


def test_4_5c_normal_allows_latest_and_active() -> None:
    assert derived_latest_projection_update_allowed("4.5c", "normal") is True
    # Job path: ops-only CAS — daily must never see CAS-required True
    assert derived_active_pointer_update_allowed("4.5c", "normal") is False


def test_replay_never_updates_shared_state() -> None:
    for stage in ("4.5a", "4.5b", "4.5c"):
        assert derived_latest_projection_update_allowed(stage, "replay") is False
        assert derived_active_pointer_update_allowed(stage, "replay") is False


def test_backfill_never_updates_latest_projection() -> None:
    for stage in ("4.5a", "4.5b", "4.5c"):
        assert derived_latest_projection_update_allowed(stage, "backfill") is False


def test_invalid_stage_raises() -> None:
    with pytest.raises(ValueError):
        normalize_phase4_5_rollout_stage("4.5d")
