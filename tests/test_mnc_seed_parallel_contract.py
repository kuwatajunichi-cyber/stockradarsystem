"""Unit: MNC seed parallel put/prefetch and --drain progress (Fake I/O)."""
from __future__ import annotations

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


def _load_worker_cli(name: str):
    import importlib.util

    cli_path = Path(__file__).resolve().parents[1] / "scripts" / "storage" / "mnc_worker_cli.py"
    spec = importlib.util.spec_from_file_location(name, cli_path)
    assert spec and spec.loader
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


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

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_under_test")
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


def test_drain_skips_when_poller_already_claimed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poller owns outbox → monthly drain exit 0 skip (not exit 2 regression)."""
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    monkeypatch.setenv("ADR005_METRIC_SET_VERSION_ID", SET_ID)
    monkeypatch.chdir(tmp_path)

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_poller_race")
    adapter = FakeSupabaseControlAdapter()
    adapter.mnc_requests[REQUEST_ID] = {
        "id": REQUEST_ID,
        "status": "series_running",
        "added_codes": ["1301"],
        "expected_trade_dates": ["2026-01-01", "2026-01-02"],
        "last_committed_trade_date": None,
    }
    adapter.mnc_outbox.append(
        {
            "id": "outbox-poller",
            "request_id": REQUEST_ID,
            "chunk_seq": 0,
            "status": "claimed",
            "claimed_by": "poller-worker:1",
            "fencing_token": 3,
            "attempt_count": 1,
            "attempt_budget": 5,
        }
    )
    monkeypatch.setattr(worker, "_adapter", lambda: adapter)
    rc = worker.main(
        ["drain-request", "--request-id", REQUEST_ID, "--github-run-id", "100"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = __import__("json").loads(out.strip().splitlines()[-1])
    assert payload.get("skipped") is True
    assert payload.get("reason") == "owned_by_other_worker"
    assert adapter.mnc_requests[REQUEST_ID]["status"] == "series_running"
    assert adapter.mnc_outbox[0]["status"] == "claimed"
    assert adapter.mnc_requests[REQUEST_ID].get("reason_code") != "worker_failed"



def test_drain_fails_when_dispatch_pending_claim_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Canonical post-snapshot state must not skip-success on empty claim."""
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    monkeypatch.setenv("ADR005_METRIC_SET_VERSION_ID", SET_ID)
    monkeypatch.chdir(tmp_path)

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_empty_claim")
    adapter = FakeSupabaseControlAdapter()
    adapter.mnc_requests[REQUEST_ID] = {
        "id": REQUEST_ID,
        "status": "dispatch_pending",
        "added_codes": ["1301"],
        "expected_trade_dates": ["2026-01-01"],
        "last_committed_trade_date": None,
    }
    adapter.mnc_outbox.append(
        {
            "id": "outbox-pending",
            "request_id": REQUEST_ID,
            "chunk_seq": 0,
            "status": "pending",
            "fencing_token": 0,
            "attempt_count": 0,
            "attempt_budget": 5,
        }
    )

    def _no_claim(*_a, **_k):
        return None

    monkeypatch.setattr(worker, "_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_claim_outbox_for_request", _no_claim)
    rc = worker.main(
        ["drain-request", "--request-id", REQUEST_ID, "--github-run-id", "101"]
    )
    assert rc == 2
    assert adapter.mnc_requests[REQUEST_ID]["status"] == "dispatch_pending"
    assert adapter.mnc_outbox[0]["status"] == "pending"


def test_claim_scoped_to_request_does_not_fail_foreign(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Request-scoped claim must not touch other request / must not call fail."""
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    monkeypatch.chdir(tmp_path)

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_foreign")
    other_id = "mnc-v1-" + ("b" * 64)
    adapter = FakeSupabaseControlAdapter()
    adapter.mnc_requests[REQUEST_ID] = {
        "id": REQUEST_ID,
        "status": "dispatch_pending",
        "added_codes": ["1301"],
        "expected_trade_dates": ["2026-01-01"],
        "last_committed_trade_date": None,
    }
    adapter.mnc_requests[other_id] = {
        "id": other_id,
        "status": "dispatch_pending",
        "added_codes": ["7203"],
        "expected_trade_dates": ["2026-01-01"],
        "last_committed_trade_date": None,
    }
    # Foreign pending outbox is first in list (global claim would grab it).
    adapter.mnc_outbox.append(
        {
            "id": "outbox-other",
            "request_id": other_id,
            "chunk_seq": 0,
            "status": "pending",
            "fencing_token": 0,
            "attempt_count": 0,
            "attempt_budget": 5,
        }
    )
    adapter.mnc_outbox.append(
        {
            "id": "outbox-mine",
            "request_id": REQUEST_ID,
            "chunk_seq": 0,
            "status": "pending",
            "fencing_token": 0,
            "attempt_count": 0,
            "attempt_budget": 5,
        }
    )
    claimed = worker._claim_outbox_for_request(
        adapter, request_id=REQUEST_ID, claimed_by="monthly-test"
    )
    assert claimed is not None
    oid, fencing = claimed
    assert oid == "outbox-mine"
    assert fencing == 1
    foreign = next(o for o in adapter.mnc_outbox if o["id"] == "outbox-other")
    assert foreign["status"] == "pending"
    assert adapter.mnc_requests[other_id]["status"] == "dispatch_pending"
    assert adapter.mnc_requests[other_id].get("reason_code") is None


def test_heartbeat_keeper_fires_during_long_work() -> None:
    import time

    worker = _load_worker_cli("mnc_worker_cli_hb")
    beats: list[int] = []

    def beat() -> None:
        beats.append(1)

    with worker._HeartbeatKeeper(beat, interval_s=0.05):
        time.sleep(0.22)
    assert len(beats) >= 2


def test_load_existing_series_state_warms_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNC_R2_CONCURRENCY", "4")
    generation_store = FakeMetricGenerationStore()
    r2_store = FakeR2ObjectStore()
    warmed: list[bool] = []

    def warm() -> None:
        warmed.append(True)

    r2_store.warm_client = warm  # type: ignore[method-assign]
    plan = plan_series_only_trade_date(
        request_id=REQUEST_ID,
        mode="series_seed",
        trade_date="2026-01-15",
        candidate_codes=["1301", "7203"],
        existing_dates_by_code={},
    )
    run_series_only_trade_date(
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
    warmed.clear()
    load_existing_series_state(
        generation_store, r2_store, SET_ID, ["1301", "7203"], 2026
    )
    assert warmed == [True]


def test_fail_mnc_outbox_rejects_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_fail_done")
    adapter = FakeSupabaseControlAdapter()
    adapter.mnc_requests[REQUEST_ID] = {
        "id": REQUEST_ID,
        "status": "series_running",
        "added_codes": ["1301"],
        "expected_trade_dates": ["2026-01-01", "2026-01-02"],
        "last_committed_trade_date": "2026-01-01",
    }
    adapter.mnc_outbox.append(
        {
            "id": "outbox-done",
            "request_id": REQUEST_ID,
            "chunk_seq": 0,
            "status": "done",
            "fencing_token": 2,
            "attempt_count": 1,
            "attempt_budget": 5,
        }
    )
    hb = worker._fake_rpc(
        adapter,
        "heartbeat_mnc_outbox",
        {"p_outbox_id": "outbox-done", "p_fencing_token": 2, "p_visibility_seconds": 1200},
    )
    assert hb.get("ok") is False
    assert hb.get("reason") == "bad_status"
    fail = worker._fake_rpc(
        adapter,
        "fail_mnc_outbox",
        {
            "p_outbox_id": "outbox-done",
            "p_fencing_token": 2,
            "p_error": "late_heartbeat",
            "p_retry_seconds": 60,
        },
    )
    assert fail.get("ok") is False
    assert fail.get("reason") == "bad_status"
    assert adapter.mnc_outbox[0]["status"] == "done"
    assert adapter.mnc_requests[REQUEST_ID]["status"] == "series_running"


def test_finish_runs_after_heartbeat_keeper_stops() -> None:
    """Structural: date-loop finish must not sit inside the Keeper with-block."""
    src = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "storage"
        / "mnc_worker_cli.py"
    ).read_text(encoding="utf-8")
    start = src.index("def cmd_run_request")
    end = src.index("def cmd_drain_request")
    body = src[start:end]
    token = "with _HeartbeatKeeper(heartbeat):"
    keeper_idx = body.index(token)
    line_start = body.rfind(chr(10), 0, keeper_idx) + 1
    with_indent = keeper_idx - line_start
    lines = body[line_start:].splitlines()
    suite: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            suite.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= with_indent:
            break
        suite.append(line)
    suite_text = chr(10).join(suite)
    assert "finish_mnc_outbox_chunk" not in suite_text
    assert "finish_mnc_outbox_chunk" in body[keeper_idx:]


def test_followup_mark_dispatched_failure_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SUPABASE_CONTROL_FAKE", "1")
    monkeypatch.setenv("DERIVED_GENERATION_FAKE", "1")
    monkeypatch.setenv("ADR005_METRIC_SET_VERSION_ID", SET_ID)
    monkeypatch.chdir(tmp_path)

    from stockradar.storage.supabase_client import FakeSupabaseControlAdapter

    worker = _load_worker_cli("mnc_worker_cli_followup_mark")
    adapter = FakeSupabaseControlAdapter()
    dates = [f"2026-01-{d:02d}" for d in range(1, 12)]
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

    real_rpc = worker._fake_rpc
    mark_calls = {"n": 0}

    def _rpc_wrap(adapter_arg, name: str, body: dict):
        if name == "mark_mnc_outbox_dispatched":
            mark_calls["n"] += 1
            if mark_calls["n"] >= 2:
                return {"ok": False, "reason": "not_found"}
        return real_rpc(adapter_arg, name, body)

    monkeypatch.setattr(worker, "_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_rpc", _rpc_wrap)
    # Drain uses --drain so one run-request may finish all dates unless we force
    # chunked run-request by calling drain which still uses drain=True.
    # Simulate follow-up by: first drain completes chunk via finish creating next,
    # but drain=True processes all dates in one cmd_run_request — next outbox only
    # appears after finish when remaining dates exist AFTER the chunk.
    # With drain=True, remaining=all dates, so finish completes request with no next.
    # Force non-drain chunking inside drain loop by patching cmd_run_request drain flag.
    original_run = worker.cmd_run_request

    def run_chunked(args):
        args.drain = False
        return original_run(args)

    monkeypatch.setattr(worker, "cmd_run_request", run_chunked)
    rc = worker.main(
        [
            "drain-request",
            "--request-id",
            REQUEST_ID,
            "--github-run-id",
            "102",
        ]
    )
    assert rc == 2
    assert mark_calls["n"] >= 2

