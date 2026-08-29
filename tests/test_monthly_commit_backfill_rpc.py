"""Fake wiring for ADR-005 monthly commit RPC."""
from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.storage.monthly_new_core import (
    build_request_id_v1,
    canonical_json_sha256_v1,
    current_core_logical_digest,
)
from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

pytestmark = pytest.mark.unit


def test_fake_commit_monthly_with_backfill_creates_outbox_only_when_runnable() -> None:
    fake = FakeSupabaseControlAdapter()
    fake.adr005_feature_start_release_month = "2026-09"
    pending = fake.insert_monthly_snapshot_pending(
        monthly_tag="monthly-20260901-1",
        snapshot_date="2026-09-01",
        github_run_id=1,
        object_keys={"core": {"object_key": "monthly/t/core.csv", "sha256": "a" * 64}},
        sha256="a" * 64,
    )
    digest = current_core_logical_digest(["7203", "9984"])
    added = ["9984"]
    added_digest = canonical_json_sha256_v1(added)
    rid = build_request_id_v1(
        release_month="2026-09",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest_hex=digest,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        added_codes=added,
    )
    result = fake.commit_monthly_snapshot_with_backfill_request(
        snapshot_id=str(pending["id"]),
        release_month="2026-09",
        request_id=rid,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest=digest,
        added_codes=added,
        added_codes_digest=added_digest,
        partition_codes_digest=added_digest,
        expected_trade_dates=["2026-08-01"],
        expected_trade_dates_digest=canonical_json_sha256_v1(["2026-08-01"]),
        calendar_version="jpx_calendar_v1",
        outcome="runnable",
    )
    assert result["outcome"] == "runnable"
    assert rid in fake.mnc_requests
    assert fake.mnc_outbox and fake.mnc_outbox[0]["request_id"] == rid
    assert fake.monthly_snapshots[str(pending["id"])]["status"] == "committed"


def test_fake_noop_has_request_without_outbox() -> None:
    fake = FakeSupabaseControlAdapter()
    pending = fake.insert_monthly_snapshot_pending(
        monthly_tag="monthly-20260901-2",
        snapshot_date="2026-09-01",
        github_run_id=2,
        object_keys={"core": {"object_key": "monthly/t2/core.csv", "sha256": "b" * 64}},
        sha256="b" * 64,
    )
    digest = current_core_logical_digest(["7203"])
    added_digest = canonical_json_sha256_v1([])
    rid = build_request_id_v1(
        release_month="2026-09",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest_hex=digest,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        added_codes=[],
    )
    fake.commit_monthly_snapshot_with_backfill_request(
        snapshot_id=str(pending["id"]),
        release_month="2026-09",
        request_id=rid,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest=digest,
        added_codes=[],
        added_codes_digest=added_digest,
        partition_codes_digest=added_digest,
        expected_trade_dates=[],
        expected_trade_dates_digest=added_digest,
        calendar_version="jpx_calendar_v1",
        outcome="noop",
    )
    assert fake.mnc_requests[rid]["status"] == "noop"
    assert fake.mnc_outbox == []


def test_migration_012_utf8_no_nul() -> None:
    raw = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "012_adr005_monthly_commit_rpc.sql"
    ).read_bytes()
    assert bytes([0]) not in raw


def test_fake_loser_does_not_insert_request() -> None:
    fake = FakeSupabaseControlAdapter()
    # First commit becomes winner
    w = fake.insert_monthly_snapshot_pending(
        monthly_tag="monthly-20260901-1",
        snapshot_date="2026-09-01",
        github_run_id=1,
        object_keys={"core": {"object_key": "monthly/w/core.csv", "sha256": "a" * 64}},
        sha256="a" * 64,
    )
    digest = current_core_logical_digest(["7203"])
    added_digest = canonical_json_sha256_v1([])
    rid = build_request_id_v1(
        release_month="2026-09",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest_hex=digest,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        added_codes=[],
    )
    fake.commit_monthly_snapshot_with_backfill_request(
        snapshot_id=str(w["id"]),
        release_month="2026-09",
        request_id=rid,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        previous_monthly_tag="monthly-20260801-1",
        current_core_logical_digest=digest,
        added_codes=[],
        added_codes_digest=added_digest,
        partition_codes_digest=added_digest,
        expected_trade_dates=[],
        expected_trade_dates_digest=added_digest,
        calendar_version="jpx_calendar_v1",
        outcome="noop",
    )
    # Later same-month snapshot with lower run_id is impossible as winner if we insert pending then commit
    # with lower id after winner exists: use run_id=0 committed after demotion scenario —
    # commit a second snapshot with LOWER run_id; canonical stays first (higher run_id wins).
    loser = fake.insert_monthly_snapshot_pending(
        monthly_tag="monthly-20260901-0",
        snapshot_date="2026-09-01",
        github_run_id=0,
        object_keys={"core": {"object_key": "monthly/l/core.csv", "sha256": "c" * 64}},
        sha256="c" * 64,
    )
    rid2 = build_request_id_v1(
        release_month="2026-09",
        previous_monthly_tag="x",
        current_core_logical_digest_hex=digest,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        added_codes=["9999"],
    )
    before_reqs = set(fake.mnc_requests)
    result = fake.commit_monthly_snapshot_with_backfill_request(
        snapshot_id=str(loser["id"]),
        release_month="2026-09",
        request_id=rid2,
        metric_set_version_id="11111111-1111-1111-1111-111111111111",
        previous_monthly_tag="x",
        current_core_logical_digest=digest,
        added_codes=["9999"],
        added_codes_digest=canonical_json_sha256_v1(["9999"]),
        partition_codes_digest=canonical_json_sha256_v1(["9999"]),
        expected_trade_dates=[],
        expected_trade_dates_digest=added_digest,
        calendar_version="jpx_calendar_v1",
        outcome="runnable",
    )
    assert result["link_role"] == "noncanonical_loser"
    assert result["request_id"] is None
    assert rid2 not in fake.mnc_requests
    assert set(fake.mnc_requests) == before_reqs
    assert any(
        link.get("monthly_snapshot_id") == str(loser["id"])
        and link.get("link_role") == "noncanonical_loser"
        and link.get("request_id") == rid
        for link in fake.mnc_release_links
    )


def test_fake_list_committed_snapshot_dates_ignores_non_snapshot() -> None:
    fake = FakeSupabaseControlAdapter()
    mid = "11111111-1111-1111-1111-111111111111"
    fake.derived_object_index = [
        {
            "metric_set_version_id": mid,
            "status": "committed",
            "object_kind": "snapshot",
            "trade_date": "2026-08-02",
        },
        {
            "metric_set_version_id": mid,
            "status": "committed",
            "object_kind": "series",
            "trade_date": "2026-08-03",
        },
        {
            "metric_set_version_id": mid,
            "status": "committed",
            "object_kind": "snapshot",
            "trade_date": "2026-08-01",
        },
        {
            "metric_set_version_id": mid,
            "status": "pending",
            "object_kind": "snapshot",
            "trade_date": "2026-08-04",
        },
    ]
    assert fake.list_committed_derived_snapshot_trade_dates(metric_set_version_id=mid) == [
        "2026-08-01",
        "2026-08-02",
    ]
