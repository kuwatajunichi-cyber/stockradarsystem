"""Contract: Phase 4.5 rollout Phase A/B/C truth tables."""
from __future__ import annotations

import pytest

from stockradar.storage.phase4_5_rollout import (
    DerivedArtifact,
    PreflightResult,
    ResolveResult,
    SetResolutionContext,
    derived_active_cas_required,
    preflight_derived_write,
    prefix_for,
    resolve_metric_set_version_id,
    write_allowed,
)

pytestmark = pytest.mark.unit

STAGES = ("off", "4.5a", "4.5b", "4.5c")
MODES = ("normal", "replay", "backfill", "reconcile")
ACTIVE_SET = "11111111-2222-3333-4444-555555555555"
FLAG_SET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

PREFLIGHT_EXPECTED = {
    ("off", "normal"): PreflightResult.SKIP0,
    ("off", "replay"): PreflightResult.SKIP0,
    ("off", "backfill"): PreflightResult.SKIP0,
    ("off", "reconcile"): PreflightResult.SKIP0,
    ("4.5a", "normal"): PreflightResult.CONTINUE,
    ("4.5a", "replay"): PreflightResult.SKIP0,
    ("4.5a", "backfill"): PreflightResult.CONTINUE,
    ("4.5a", "reconcile"): PreflightResult.EXIT2,
    ("4.5b", "normal"): PreflightResult.CONTINUE,
    ("4.5b", "replay"): PreflightResult.SKIP0,
    ("4.5b", "backfill"): PreflightResult.CONTINUE,
    ("4.5b", "reconcile"): PreflightResult.EXIT2,
    ("4.5c", "normal"): PreflightResult.CONTINUE,
    ("4.5c", "replay"): PreflightResult.SKIP0,
    ("4.5c", "backfill"): PreflightResult.CONTINUE,
    ("4.5c", "reconcile"): PreflightResult.CONTINUE,
}

RESOLVE_EXPECTED = {
    ("off", "normal"): (ResolveResult.SKIP0, None),
    ("off", "replay"): (ResolveResult.SKIP0, None),
    ("off", "backfill"): (ResolveResult.SKIP0, None),
    ("off", "reconcile"): (ResolveResult.SKIP0, None),
    ("4.5a", "normal"): (ResolveResult.FLAG_REQUIRED, None),
    ("4.5a", "replay"): (ResolveResult.NO_RESOLVE_REPLAY, None),
    ("4.5a", "backfill"): (ResolveResult.FLAG_REQUIRED, None),
    ("4.5a", "reconcile"): (ResolveResult.EXIT2, None),
    ("4.5b", "normal"): (ResolveResult.FLAG_REQUIRED, None),
    ("4.5b", "replay"): (ResolveResult.NO_RESOLVE_REPLAY, None),
    ("4.5b", "backfill"): (ResolveResult.FLAG_REQUIRED, None),
    ("4.5b", "reconcile"): (ResolveResult.EXIT2, None),
    ("4.5c", "normal"): (ResolveResult.RESOLVE_ACTIVE, ACTIVE_SET),
    ("4.5c", "replay"): (ResolveResult.NO_RESOLVE_REPLAY, None),
    ("4.5c", "backfill"): (ResolveResult.FLAG_REQUIRED, None),
    ("4.5c", "reconcile"): (ResolveResult.FLAG_MUST_MATCH_ACTIVE, None),
}


@pytest.mark.unit
@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("mode", MODES)
def test_preflight_derived_write_matrix(stage: str, mode: str) -> None:
    expected = PREFLIGHT_EXPECTED[(stage, mode)]
    assert preflight_derived_write(stage, mode) == expected


@pytest.mark.unit
@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("mode", MODES)
def test_resolve_metric_set_version_id_matrix(stage: str, mode: str) -> None:
    ctx = SetResolutionContext(active_metric_set_id=ACTIVE_SET)
    expected_result, expected_uuid = RESOLVE_EXPECTED[(stage, mode)]
    result, uuid = resolve_metric_set_version_id(stage=stage, mode=mode, ctx=ctx)
    assert result == expected_result
    assert uuid == expected_uuid


@pytest.mark.unit
def test_resolve_use_uuid_when_flag_present() -> None:
    result, uuid = resolve_metric_set_version_id(
        stage="4.5a",
        mode="normal",
        metric_set_version_id=f"  {FLAG_SET.upper()}  ",
    )
    assert result == ResolveResult.USE_UUID
    assert uuid == FLAG_SET


@pytest.mark.unit
def test_4_5a_normal_series_write_denied() -> None:
    assert (
        write_allowed(
            stage="4.5a",
            mode="normal",
            set_is_active=False,
            set_lifecycle="shadow",
            artifact=DerivedArtifact.SERIES,
        )
        is False
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "stage,mode,lifecycle,is_active,artifact,expected",
    [
        ("4.5a", "normal", "shadow", False, DerivedArtifact.SNAPSHOT, True),
        ("4.5a", "normal", "shadow", False, DerivedArtifact.GENERATION_INDEX, True),
        ("4.5a", "normal", "shadow", False, DerivedArtifact.LATEST, False),
        ("4.5b", "normal", "shadow", False, DerivedArtifact.SERIES, True),
        ("4.5c", "normal", "active", True, DerivedArtifact.LATEST, True),
        ("4.5c", "normal", "shadow", False, DerivedArtifact.SNAPSHOT, False),
        ("off", "normal", "shadow", False, DerivedArtifact.SNAPSHOT, False),
        ("4.5c", "replay", "active", True, DerivedArtifact.SNAPSHOT, False),
        ("4.5a", "backfill", "shadow", False, DerivedArtifact.LATEST, False),
    ],
)
def test_write_allowed_matrix(
    stage: str,
    mode: str,
    lifecycle: str,
    is_active: bool,
    artifact: DerivedArtifact,
    expected: bool,
) -> None:
    assert (
        write_allowed(
            stage=stage,
            mode=mode,
            set_is_active=is_active,
            set_lifecycle=lifecycle,
            artifact=artifact,
        )
        == expected
    )


@pytest.mark.unit
def test_prefix_for_has_no_shadow_or_prod_tokens() -> None:
    prefixes = prefix_for(ACTIVE_SET)
    combined = f"{prefixes.snapshot_prefix}|{prefixes.series_prefix}".lower()
    assert "shadow" not in combined
    assert "prod" not in combined
    assert ACTIVE_SET in prefixes.snapshot_prefix
    assert ACTIVE_SET in prefixes.series_prefix


@pytest.mark.unit
@pytest.mark.parametrize("stage", STAGES)
def test_derived_active_cas_required_always_false(stage: str) -> None:
    assert derived_active_cas_required(stage) is False
