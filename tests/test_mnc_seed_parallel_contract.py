"""Unit: MNC seed parallel put/prefetch and --drain progress (Fake I/O)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stockradar.jobs.write_series_only_generation import (
    ExistingSeriesState,
    _put_registered_objects_parallel,
    _r2_concurrency,
    load_existing_series_state,
    plan_series_only_trade_date,
    run_series_only_trade_date,
)
from stockradar.storage.derived_generation import FakeMetricGenerationStore
from stockradar.storage.r2_object_store import FakeR2ObjectStore

pytestmark = pytest.mark.unit

SET_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
REQUEST_ID = "mnc-v1-" + ("a" * 64)
METRIC_KEYS = ["rs31_topix", "price_change_pct"]
FINGERPRINT = "b" * 64


def test_r2_concurrency_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MNC_R2_CONCURRENCY", raising=False)
    monkeypatch.delenv("DERIVED_R2_CONCURRENCY", raising=False)
    assert _r2_concurrency() == 32
    monkeypatch.setenv("MNC_R2_CONCURRENCY", "16")
    assert _r2_concurrency() == 16


def test_put_registered_objects_parallel_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNC_R2_CONCURRENCY", "4")
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    plan = plan_series_only_trade_date(
        request_id=REQUEST_ID,
        mode="series_seed",
        trade_date="2026-01-15",
        candidate_codes=["1301", "7203"],
        existing_dates_by_code={},
    )
    generation_id = run_series_only_trade_date(
        plan=plan,
        metric_set_version_id=SET_ID,
        github_run_id=7,
        values_by_code={
            "1301": {"rs31_topix": 1.0, "price_change_pct": 0.1},
            "7203": {"rs31_topix": 2.0, "price_change_pct": -0.2},
        },
        existing_state=ExistingSeriesState(),
        generation_store=generation_store,
        r2_store=r2_store,
        metric_keys_ordered=METRIC_KEYS,
        set_fingerprint=FINGERPRINT,
    )
    assert generation_id is not None
    for code in ("1301", "7203"):
        key = generation_store.get_committed_series_object_key(
            metric_set_version_id=SET_ID,
            instrument_code=code,
            series_year=2026,
        )
        assert key
        assert key in r2_store.objects


def test_load_existing_series_state_parallel_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNC_R2_CONCURRENCY", "4")
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    plan = plan_series_only_trade_date(
        request_id=REQUEST_ID,
        mode="series_seed",
        trade_date="2026-01-15",
        candidate_codes=["1301"],
        existing_dates_by_code={},
    )
    run_series_only_trade_date(
        plan=plan,
        metric_set_version_id=SET_ID,
        github_run_id=7,
        values_by_code={"1301": {"rs31_topix": 1.0, "price_change_pct": 0.1}},
        existing_state=ExistingSeriesState(),
        generation_store=generation_store,
        r2_store=r2_store,
        metric_keys_ordered=METRIC_KEYS,
        set_fingerprint=FINGERPRINT,
    )
    state = load_existing_series_state(
        generation_store, r2_store, SET_ID, ["1301"], 2026
    )
    assert "1301" in state.dates_by_code
    assert "2026-01-15" in state.dates_by_code["1301"]


def test_put_registered_objects_parallel_empty() -> None:
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    assert (
        _put_registered_objects_parallel(
            generation_store=generation_store,
            r2_store=r2_store,
            generation_id="00000000-0000-0000-0000-000000000001",
            items=[],
        )
        == []
    )


def test_drain_request_advances_all_trade_dates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    monkeypatch.setenv("ADR005_METRIC_SET_VERSION_ID", SET_ID)
    monkeypatch.chdir(tmp_path)

    import importlib.util

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    cli_path = Path(__file__).resolve().parents[1] / "scripts" / "storage" / "mnc_worker_cli.py"
    spec = importlib.util.spec_from_file_location("mnc_worker_cli_under_test", cli_path)
    assert spec and spec.loader
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    adapter = FakeSupabaseControlAdapter()
    dates = [f"2026-01-{d:02d}" for d in range(1, 16)]  # 15 days > chunk size 10
    adapter.mnc_requests[REQUEST_ID] = {
        "id": REQUEST_ID,
        "status": "dispatch_pending",
        "added_codes": ["1301"],
        "expected_trade_dates": dates,
        "last_committed_trade_date": None,
    }
    adapter.mnc_outbox.append(
        {
            "id": "outbox-0",
            "request_id": REQUEST_ID,
            "chunk_seq": 0,
            "status": "pending",
            "fencing_token": 0,
            "attempt_count": 0,
            "attempt_budget": 5,
        }
    )

    monkeypatch.setattr(worker, "_adapter", lambda: adapter)
    rc = worker.main(
        [
            "drain-request",
            "--request-id",
            REQUEST_ID,
            "--github-run-id",
            "99",
        ]
    )
    assert rc == 0
    req = adapter.mnc_requests[REQUEST_ID]
    assert req["last_committed_trade_date"] == dates[-1]
    assert req["status"] == "completed"
