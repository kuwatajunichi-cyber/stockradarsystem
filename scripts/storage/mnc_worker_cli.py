"""ADR-005 worker: series_seed (chunk or --drain) with outbox fencing/heartbeat."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.config import (  # noqa: E402
    get_buffer_days,
    get_rs_benchmark,
    get_rs_windows,
    get_yf_daily_cache_dir,
    get_yf_index_cache_dir,
    get_z_lookback_days,
)
from stockradar.jobs.compute_indicators_for_core import (  # noqa: E402
    _compute_one_code,
    _init_worker,
    max_ohlc_date_on_or_before,
)
from stockradar.jobs.ensure_index_cache import BENCHMARKS  # noqa: E402
from stockradar.jobs.write_series_only_generation import (  # noqa: E402
    ExistingSeriesState,
    ensure_seed_catalog_or_block,
    load_existing_series_state,
    plan_series_only_trade_date,
    run_series_only_trade_date,
)
from stockradar.metrics.registry_spec import load_metric_set_spec  # noqa: E402
from stockradar.storage.derived_adapters import (  # noqa: E402
    generation_store_from_env,
    is_derived_generation_fake,
    r2_store_from_env,
)
from stockradar.storage.supabase_client import (  # noqa: E402
    FakeSupabaseControlAdapter,
    SupabaseRestAdapter,
)
from stockradar.utils.paths import ticker_for_code  # noqa: E402
from stockradar.utils.yf_cache import (  # noqa: E402
    MANIFEST_FILENAME,
    ensure_cache_with_incremental_fetch,
    load_cache,
    load_manifest,
    update_manifest,
)

MAX_TRADE_DATES_PER_CHUNK = 10
DEFAULT_VISIBILITY_SECONDS = 1200
DRAIN_VISIBILITY_SECONDS = 7200
HEARTBEAT_INTERVAL_SECONDS = 45
DEFAULT_CODE_CONCURRENCY = 8

_TERMINAL_SKIP_REQUEST_STATUSES = frozenset(
    {
        "completed",
        "noop",
        "blocked",
        "grandfather",
        "superseded",
        "paused",
    }
)
_ACTIVE_OUTBOX_STATUSES = frozenset({"claimed", "dispatched"})


class FencingMismatch(Exception):
    """Outbox fencing token no longer owned by this worker."""


def _code_concurrency() -> int:
    raw = os.environ.get("MNC_CODE_CONCURRENCY", str(DEFAULT_CODE_CONCURRENCY)).strip()
    try:
        value = int(raw or DEFAULT_CODE_CONCURRENCY)
    except ValueError:
        value = DEFAULT_CODE_CONCURRENCY
    return max(1, min(32, value))


def _adapter():
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return FakeSupabaseControlAdapter()
    return SupabaseRestAdapter.from_env()


def _is_fake(adapter) -> bool:
    return isinstance(adapter, FakeSupabaseControlAdapter) or is_derived_generation_fake()


def _rpc(adapter, name: str, body: dict[str, Any]) -> dict[str, Any]:
    if isinstance(adapter, FakeSupabaseControlAdapter):
        return _fake_rpc(adapter, name, body)
    resp = adapter._request("POST", f"/rest/v1/rpc/{name}", json_body=body)
    resp.raise_for_status()
    payload = resp.json()
    if name == "claim_mnc_outbox":
        # PostgREST may return a single object for one row, not a one-element list.
        if isinstance(payload, list):
            rows = list(payload)
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            rows = []
        return {"ok": True, "rows": rows}
    if isinstance(payload, dict):
        return payload
    return {"ok": True, "result": payload}


def _fake_rpc(adapter: FakeSupabaseControlAdapter, name: str, body: dict[str, Any]) -> dict[str, Any]:
    outbox_id = str(body.get("p_outbox_id") or "")
    fencing = int(body.get("p_fencing_token") or 0)
    row = next((o for o in adapter.mnc_outbox if str(o.get("id")) == outbox_id), None)
    if name == "claim_mnc_outbox":
        limit = int(body.get("p_limit") or 1)
        claimed_by = str(body.get("p_claimed_by") or "fake-worker")
        want_request = str(body.get("p_request_id") or "").strip()
        claimed: list[dict[str, Any]] = []
        for o in adapter.mnc_outbox:
            if len(claimed) >= max(1, min(2, limit)):
                break
            status = str(o.get("status") or "")
            if status == "pending":
                pass
            elif status == "failed":
                # Mirror SQL: failed is claimable only when next_retry_at has been reached.
                nra = str(o.get("next_retry_at") or "").strip()
                if nra and nra not in {"ready", "fake-ready"}:
                    continue
            else:
                continue
            rid = str(o.get("request_id") or "")
            if want_request and rid != want_request:
                continue
            req = adapter.mnc_requests.get(rid) or {}
            if str(req.get("status") or "") in _TERMINAL_SKIP_REQUEST_STATUSES:
                continue
            o["status"] = "claimed"
            o["claimed_by"] = claimed_by
            o["fencing_token"] = int(o.get("fencing_token") or 0) + 1
            o["attempt_count"] = int(o.get("attempt_count") or 0) + 1
            claimed.append(dict(o))
        return {"ok": True, "rows": claimed}
    if name == "mark_mnc_outbox_dispatched":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        row["status"] = "dispatched"
        row["github_run_id"] = int(body.get("p_github_run_id") or 0)
        return {"ok": True, "outbox_id": outbox_id}
    if name == "heartbeat_mnc_outbox":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        if str(row.get("status") or "") not in {"claimed", "dispatched"}:
            return {"ok": False, "reason": "bad_status", "status": row.get("status")}
        count = int(row.get("heartbeat_count") or 0) + 1
        row["heartbeat_count"] = count
        row["heartbeat_at"] = f"fake-ts-{count}"
        row["visibility_timeout_at"] = f"fake+{int(body.get('p_visibility_seconds') or DEFAULT_VISIBILITY_SECONDS)}s"
        return {"ok": True, "outbox_id": outbox_id}
    if name == "fail_mnc_outbox":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        # Defense: never rewind a successfully finished chunk.
        if str(row.get("status") or "") == "done":
            return {"ok": False, "reason": "bad_status", "status": "done"}
        row["status"] = "failed"
        row["last_error"] = str(body.get("p_error") or "worker_failed")[:2000]
        retry = max(60, min(int(body.get("p_retry_seconds") or 300), 86400))
        row["next_retry_at"] = f"fake+{retry}s"
        request_id = str(row.get("request_id") or "")
        req = adapter.mnc_requests.get(request_id)
        if req is not None and str(req.get("status") or "") not in _TERMINAL_SKIP_REQUEST_STATUSES:
            req["status"] = "failed_retryable"
            req["reason_code"] = "worker_failed"
        return {"ok": True, "outbox_id": outbox_id, "status": "failed"}
    if name == "finish_mnc_outbox_chunk":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        row["status"] = "done"
        request_id = str(row.get("request_id") or "")
        req = adapter.mnc_requests.get(request_id)
        if req is not None:
            expected = req.get("expected_trade_dates") or []
            if isinstance(expected, str):
                expected = json.loads(expected)
            last = req.get("last_committed_trade_date")
            remaining = [d for d in expected if last is None or str(d) > str(last)]
            if not remaining:
                req["status"] = "completed"
            else:
                req["status"] = "series_running"
                next_seq = int(row.get("chunk_seq") or 0) + 1
                adapter.mnc_outbox.append(
                    {
                        "id": f"outbox-next-{next_seq}",
                        "request_id": request_id,
                        "chunk_seq": next_seq,
                        "status": "pending",
                        "fencing_token": 0,
                        "attempt_count": 0,
                        "attempt_budget": 5,
                    }
                )
        return {"ok": True, "outbox_id": outbox_id, "status": row["status"]}
    if name == "commit_trade_date_progress":
        request_id = str(body.get("p_request_id") or "")
        req = adapter.mnc_requests.get(request_id)
        if req is None:
            raise RuntimeError(f"request not found: {request_id}")
        trade_date = str(body.get("p_trade_date") or "")
        req["last_committed_trade_date"] = trade_date
        if req.get("status") in {
            "dispatch_pending",
            "dispatched",
            "ohlcv_running",
            "ohlcv_ready",
        }:
            req["status"] = "series_running"
        return {
            "request_id": request_id,
            "trade_date": trade_date,
            "write_count": int(body.get("p_write_count") or 0),
            "resolved_noop_count": int(body.get("p_resolved_noop_count") or 0),
            "generation_id": body.get("p_generation_id"),
        }
    raise RuntimeError(f"unsupported fake rpc: {name}")


def _require_ok(payload: dict[str, Any], *, action: str) -> None:
    if payload.get("ok") is False:
        reason = str(payload.get("reason") or "unknown")
        if reason == "fencing_mismatch":
            raise FencingMismatch(f"{action}: fencing_mismatch")
        raise RuntimeError(f"{action} failed: {payload}")


def _load_request(adapter, request_id: str) -> dict:
    if isinstance(adapter, FakeSupabaseControlAdapter):
        row = adapter.mnc_requests.get(request_id)
        if not row:
            raise RuntimeError(f"request not found: {request_id}")
        return dict(row)
    resp = adapter._request(
        "GET",
        "/rest/v1/monthly_new_core_backfill_requests",
        params={"id": f"eq.{request_id}", "select": "*"},
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"request not found: {request_id}")
    return dict(rows[0])


def _required_days() -> int:
    rs_windows = get_rs_windows()
    rs_max = max(rs_windows) if rs_windows else 252
    return max(rs_max, get_z_lookback_days()) + get_buffer_days()


def _raise_if_cache_not_ok(kind: str, name: str, ent: dict[str, Any]) -> None:
    status = str(ent.get("status") or "")
    if status == "ok":
        return
    # New listings often have fewer bars than required_days; Daily/seed compute
    # already emits nulls for metrics that need longer history.
    if kind == "ohlcv" and status == "insufficient":
        print(
            f"warning: ohlcv cache insufficient for {name}: {ent.get('error')}; "
            "continuing with available bars",
            file=sys.stderr,
        )
        return
    raise RuntimeError(
        f"{kind} cache {status} for {name}: {ent.get('error') or status}"
    )


def _ensure_layer1_caches(*, codes: list[str], trade_date: date) -> None:
    base = Path.cwd()
    daily_dir = get_yf_daily_cache_dir(base)
    index_dir = get_yf_index_cache_dir(base)
    daily_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    required_days = _required_days()
    workers = _code_concurrency()

    daily_manifest_path = daily_dir / MANIFEST_FILENAME
    daily_manifest = load_manifest(daily_manifest_path)

    def _fetch_one(code: str) -> tuple[str, dict[str, Any]]:
        ticker = ticker_for_code(code)
        # Per-code manifest copy avoids concurrent mutation of the shared dict.
        local_manifest = dict(daily_manifest)
        ent = ensure_cache_with_incremental_fetch(
            symbol=code,
            ticker=ticker,
            cache_path=daily_dir / f"{code}.csv",
            manifest=local_manifest,
            required_days=required_days,
            run_date=trade_date,
        )
        return code, ent

    if workers == 1 or len(codes) <= 1:
        results = [_fetch_one(code) for code in codes]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(codes))) as pool:
            results = list(pool.map(_fetch_one, codes))
    for code, ent in results:
        daily_manifest[code] = ent
        _raise_if_cache_not_ok("ohlcv", code, ent)
    update_manifest(daily_manifest_path, daily_manifest)

    # Match ensure_index_cache: manifest key is the yfinance ticker (^N225 / 1306.T).
    index_manifest_path = index_dir / MANIFEST_FILENAME
    index_manifest = load_manifest(index_manifest_path)
    max_passes = 3
    stale_sleep_sec = 5
    for pass_i in range(max_passes):
        pending = list(BENCHMARKS.items())
        if pass_i > 0:
            pending = [
                (name, ticker)
                for name, ticker in BENCHMARKS.items()
                if str((index_manifest.get(ticker) or {}).get("status") or "") != "ok"
            ]
            if not pending:
                break
            time.sleep(stale_sleep_sec)
        for name, ticker in pending:
            ent = ensure_cache_with_incremental_fetch(
                symbol=ticker,
                ticker=ticker,
                cache_path=index_dir / f"{name}.csv",
                manifest=index_manifest,
                required_days=required_days,
                run_date=trade_date,
                force=(pass_i == max_passes - 1),
            )
            index_manifest[ticker] = ent
    update_manifest(index_manifest_path, index_manifest)
    for name, ticker in BENCHMARKS.items():
        ent = index_manifest.get(ticker) or {}
        status = str(ent.get("status") or "")
        if status == "ok":
            continue
        # Daily RS path already asof-merges benchmark bars. Keep writing when the
        # equity bar exists but index feed lags a session after retries.
        if status == "stale":
            print(
                f"warning: index cache stale for {name} ({ticker}) on {trade_date}; "
                "continuing with asof benchmark bars",
                file=sys.stderr,
            )
            continue
        _raise_if_cache_not_ok("index", name, ent)


def _load_benchmarks(run_date: date) -> dict[str, pd.DataFrame]:
    index_dir = get_yf_index_cache_dir(Path.cwd())
    rs_benchmark = get_rs_benchmark()
    benchmarks: dict[str, pd.DataFrame] = {}
    if rs_benchmark in ("TOPIX", "BOTH"):
        topix = load_cache(index_dir / "topix.csv")
        if topix is not None:
            benchmarks["topix"] = topix
    if rs_benchmark in ("NIKKEI", "BOTH"):
        nikkei = load_cache(index_dir / "nikkei.csv")
        if nikkei is not None:
            benchmarks["nikkei"] = nikkei
    if not benchmarks:
        raise RuntimeError("benchmark cache unavailable")
    for name, df in benchmarks.items():
        md = max_ohlc_date_on_or_before(df, run_date)
        if md is None:
            raise RuntimeError(f"benchmark {name} has no OHLC on or before {run_date}")
        if md < run_date:
            print(
                f"warning: benchmark {name} latest OHLC {md} is before trade_date "
                f"{run_date}; using asof bars",
                file=sys.stderr,
            )
    return {k: v[v.index.date <= run_date] for k, v in benchmarks.items()}


def _row_to_metric_values(row: dict[str, Any], metric_keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in metric_keys:
        raw = row.get(key)
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            out[key] = None
        else:
            try:
                out[key] = float(raw)
            except (TypeError, ValueError):
                out[key] = None
    return out


def compute_metric_values_for_codes(
    *,
    codes: list[str],
    trade_date: str,
    metric_keys_ordered: list[str],
    ensure_layer1: bool = True,
) -> dict[str, dict[str, Any]]:
    """Ensure Layer1 caches and compute catalog metrics for write_codes.

    When DERIVED_GENERATION_FAKE / SUPABASE_CONTROL_FAKE is set, returns null values
    (no yfinance I/O) so Secrets-free tests can exercise the write path.
    """
    if is_derived_generation_fake() or os.environ.get(
        "SUPABASE_CONTROL_FAKE", ""
    ).strip().lower() in ("1", "true", "yes"):
        return {code: {key: None for key in metric_keys_ordered} for code in codes}

    run_date = date.fromisoformat(trade_date)
    if ensure_layer1:
        _ensure_layer1_caches(codes=codes, trade_date=run_date)
    benchmarks = _load_benchmarks(run_date)
    daily_dir = get_yf_daily_cache_dir(Path.cwd())
    worker_ctx = {
        "run_date": run_date,
        "daily_cache_dir": str(daily_dir),
        "z_lookback_days": get_z_lookback_days(),
        "rs_windows": get_rs_windows(),
        "benchmarks": benchmarks,
        "compute_candle": False,
    }
    _init_worker(worker_ctx)
    values: dict[str, dict[str, Any]] = {}
    workers = _code_concurrency()

    def _one(code: str) -> tuple[str, dict[str, Any]]:
        result = _compute_one_code((code, ""))
        status = str(result.get("status") or "")
        if status == "missing":
            raise RuntimeError(f"ohlcv missing for code={code} trade_date={trade_date}")
        if status == "stale_ohlc":
            raise RuntimeError(f"ohlcv stale for code={code} trade_date={trade_date}")
        row = dict(result.get("row") or {})
        return code, _row_to_metric_values(row, metric_keys_ordered)

    if workers == 1 or len(codes) <= 1:
        for code in codes:
            c, vals = _one(code)
            values[c] = vals
        return values

    with ThreadPoolExecutor(max_workers=min(workers, len(codes))) as pool:
        futures = {pool.submit(_one, code): code for code in codes}
        for fut in as_completed(futures):
            code, vals = fut.result()
            values[code] = vals
    return values


class _HeartbeatKeeper:
    """Periodic outbox heartbeat during long Layer1 / R2 stretches (ADR ≤60s)."""

    def __init__(self, beat: Callable[[], None], *, interval_s: float = HEARTBEAT_INTERVAL_SECONDS):
        self._beat = beat
        self._interval_s = max(0.01, float(interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def __enter__(self) -> "_HeartbeatKeeper":
        self._thread = threading.Thread(target=self._loop, name="mnc-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                self._beat()
            except BaseException as exc:  # noqa: BLE001 — surface to owner thread
                self._error = exc
                break

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s + 5)
        if self._error is not None and exc_type is None:
            raise self._error


def _list_outbox_for_request(adapter, request_id: str) -> list[dict[str, Any]]:
    rid = request_id.strip()
    if isinstance(adapter, FakeSupabaseControlAdapter):
        return [dict(o) for o in adapter.mnc_outbox if str(o.get("request_id") or "") == rid]
    resp = adapter._request(
        "GET",
        "/rest/v1/monthly_new_core_backfill_outbox",
        params={
            "request_id": f"eq.{rid}",
            "select": "id,request_id,status,claimed_by,fencing_token,chunk_seq,github_run_id",
            "order": "chunk_seq",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    return list(rows) if isinstance(rows, list) else []


def _skip_owned_elsewhere_payload(
    *,
    request_id: str,
    request_status: str,
    outbox_rows: list[dict[str, Any]],
    detail: str,
) -> dict[str, Any]:
    active = [
        {
            "id": str(o.get("id") or ""),
            "status": str(o.get("status") or ""),
            "claimed_by": o.get("claimed_by"),
            "github_run_id": o.get("github_run_id"),
        }
        for o in outbox_rows
        if str(o.get("status") or "") in _ACTIVE_OUTBOX_STATUSES
    ]
    return {
        "status": "ok",
        "skipped": True,
        "reason": "owned_by_other_worker",
        "request_id": request_id,
        "request_status": request_status,
        "active_outbox": active,
        "detail": detail,
    }


def _foreign_active_outbox(
    outbox_rows: list[dict[str, Any]], *, claimed_by: str
) -> list[dict[str, Any]]:
    """Active outbox rows owned by someone other than this worker."""
    me = claimed_by.strip()
    foreign: list[dict[str, Any]] = []
    for o in outbox_rows:
        if str(o.get("status") or "") not in _ACTIVE_OUTBOX_STATUSES:
            continue
        owner = str(o.get("claimed_by") or "").strip()
        if owner and owner == me:
            continue
        if owner:
            foreign.append(o)
    return foreign


def _claim_outbox_for_request(
    adapter,
    *,
    request_id: str,
    claimed_by: str,
    visibility_seconds: int = DEFAULT_VISIBILITY_SECONDS,
) -> tuple[str, int] | None:
    """Claim pending/failed-retryable outbox for this request_id only (never poisons others)."""
    payload = _rpc(
        adapter,
        "claim_mnc_outbox",
        {
            "p_claimed_by": claimed_by,
            "p_limit": 1,
            "p_visibility_seconds": int(visibility_seconds),
            "p_request_id": request_id,
        },
    )
    rows = list(payload.get("rows") or [])
    if not rows:
        return None
    row = rows[0]
    if str(row.get("request_id") or "") != request_id:
        # Defense in depth: request-scoped RPC must not return foreign rows.
        print(
            json.dumps(
                {
                    "status": "warning",
                    "reason": "claim_returned_foreign_request",
                    "expected": request_id,
                    "got": row.get("request_id"),
                }
            ),
            file=sys.stderr,
        )
        return None
    return str(row.get("id") or ""), int(row.get("fencing_token") or 0)


def cmd_run_request(args: argparse.Namespace) -> int:
    ensure_seed_catalog_or_block()
    adapter = _adapter()
    outbox_id = str(args.outbox_id or "").strip()
    fencing_token = str(args.fencing_token or "").strip()
    github_run_id = int(args.github_run_id or 0)
    repository = os.environ.get("GITHUB_REPOSITORY", "local/stockradarsystem").strip()
    drain = bool(getattr(args, "drain", False))
    writer_workflow = str(
        getattr(args, "writer_workflow", "") or "monthly_new_core_backfill.yml"
    ).strip()
    visibility = DRAIN_VISIBILITY_SECONDS if drain else DEFAULT_VISIBILITY_SECONDS

    if not _is_fake(adapter) and (not outbox_id or not fencing_token):
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "outbox_id and fencing_token required outside FAKE mode",
                }
            ),
            file=sys.stderr,
        )
        return 2

    fencing_int = int(fencing_token or 0)

    def heartbeat() -> None:
        if not outbox_id:
            return
        payload = _rpc(
            adapter,
            "heartbeat_mnc_outbox",
            {
                "p_outbox_id": outbox_id,
                "p_fencing_token": fencing_int,
                "p_visibility_seconds": visibility,
            },
        )
        # After finish (or concurrent race) outbox is no longer claimed/dispatched.
        if payload.get("ok") is False and str(payload.get("reason") or "") == "bad_status":
            return
        _require_ok(payload, action="heartbeat_mnc_outbox")

    try:
        heartbeat()
        req = _load_request(adapter, args.request_id)
        status = str(req.get("status") or "")
        if status in _TERMINAL_SKIP_REQUEST_STATUSES:
            print(
                json.dumps(
                    {"status": "ok", "skipped": True, "request_status": status},
                    ensure_ascii=False,
                )
            )
            return 0

        codes_raw = req.get("added_codes") or []
        if isinstance(codes_raw, str):
            codes_raw = json.loads(codes_raw)
        codes = [str(c).strip() for c in codes_raw if str(c).strip()]
        expected_dates = req.get("expected_trade_dates") or []
        if isinstance(expected_dates, str):
            expected_dates = json.loads(expected_dates)
        last = req.get("last_committed_trade_date")
        remaining = [str(d) for d in expected_dates if last is None or str(d) > str(last)]
        if not remaining:
            if outbox_id:
                finish = _rpc(
                    adapter,
                    "finish_mnc_outbox_chunk",
                    {"p_outbox_id": outbox_id, "p_fencing_token": fencing_int},
                )
                _require_ok(finish, action="finish_mnc_outbox_chunk")
            print(
                json.dumps(
                    {"status": "ok", "done": True, "reason": "no_remaining_trade_dates"},
                    ensure_ascii=False,
                )
            )
            return 0

        chunk = remaining if drain else remaining[:MAX_TRADE_DATES_PER_CHUNK]
        metric_set_version_id = (
            os.environ.get("ADR005_METRIC_SET_VERSION_ID", "").strip()
            or "00000000-0000-0000-0000-000000000001"
        )
        spec = load_metric_set_spec()
        metric_keys = spec.metric_keys_ordered
        generation_store = generation_store_from_env()
        r2_store = r2_store_from_env()

        day_summaries: list[dict[str, Any]] = []
        layer1_hoisted = False
        finish_payload: dict[str, Any] | None = None
        t0 = time.perf_counter()

        # Finish must run after Keeper stops: heartbeat rejects non-claimed/dispatched
        # (bad_status) and must not rewind a successful finish via fail_mnc_outbox.
        with _HeartbeatKeeper(heartbeat):
            years = sorted({int(td[:4]) for td in chunk})
            existing = ExistingSeriesState()
            try:
                for year in years:
                    partial = load_existing_series_state(
                        generation_store,
                        r2_store,
                        metric_set_version_id,
                        codes,
                        year,
                    )
                    existing.dates_by_code.update(partial.dates_by_code)
                    existing.series_by_code.update(partial.series_by_code)
                    existing.flags_by_code.update(partial.flags_by_code)
                    existing.prior_digest_by_code.update(partial.prior_digest_by_code)
            except Exception as exc:
                if _is_fake(adapter):
                    print(
                        f"warning: load_existing_series_state failed in FAKE mode: {exc}",
                        file=sys.stderr,
                    )
                    existing = ExistingSeriesState()
                else:
                    raise

            # ADR: Layer1 ensure once per request (use coverage end as run_date).
            if not (
                is_derived_generation_fake()
                or os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower()
                in ("1", "true", "yes")
            ):
                _ensure_layer1_caches(
                    codes=codes,
                    trade_date=date.fromisoformat(chunk[-1]),
                )
                layer1_hoisted = True

            for trade_date in chunk:
                heartbeat()
                plan = plan_series_only_trade_date(
                    request_id=args.request_id,
                    mode="series_seed",
                    trade_date=trade_date,
                    candidate_codes=codes,
                    existing_dates_by_code=existing.dates_by_code,
                )
                generation_id: str | None = None
                if plan.expected_object_count > 0:
                    values = compute_metric_values_for_codes(
                        codes=list(plan.write_codes),
                        trade_date=trade_date,
                        metric_keys_ordered=metric_keys,
                        ensure_layer1=not layer1_hoisted,
                    )
                    generation_id = run_series_only_trade_date(
                        plan=plan,
                        metric_set_version_id=metric_set_version_id,
                        github_run_id=github_run_id,
                        values_by_code=values,
                        existing_state=existing,
                        generation_store=generation_store,
                        r2_store=r2_store,
                        metric_keys_ordered=metric_keys,
                        set_fingerprint=spec.set_fingerprint,
                        repository=repository,
                        writer_workflow=writer_workflow,
                    )
                    year = int(trade_date[:4])
                    refreshed = load_existing_series_state(
                        generation_store,
                        r2_store,
                        metric_set_version_id,
                        list(plan.write_codes),
                        year,
                    )
                    existing.dates_by_code.update(refreshed.dates_by_code)
                    existing.series_by_code.update(refreshed.series_by_code)
                    existing.flags_by_code.update(refreshed.flags_by_code)
                    existing.prior_digest_by_code.update(refreshed.prior_digest_by_code)

                progress = _rpc(
                    adapter,
                    "commit_trade_date_progress",
                    {
                        "p_request_id": args.request_id,
                        "p_trade_date": trade_date,
                        "p_write_count": len(plan.write_codes),
                        "p_resolved_noop_count": len(plan.resolved_noop_codes),
                        "p_generation_id": generation_id,
                    },
                )
                day_summaries.append(
                    {
                        "trade_date": trade_date,
                        "write_codes": list(plan.write_codes),
                        "resolved_noop_codes": list(plan.resolved_noop_codes),
                        "expected_object_count": plan.expected_object_count,
                        "generation_id": generation_id,
                        "progress": progress,
                    }
                )

        if outbox_id:
            finish_payload = _rpc(
                adapter,
                "finish_mnc_outbox_chunk",
                {"p_outbox_id": outbox_id, "p_fencing_token": fencing_int},
            )
            _require_ok(finish_payload, action="finish_mnc_outbox_chunk")

        wall_ms = int((time.perf_counter() - t0) * 1000)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "request_id": args.request_id,
                    "outbox_id": outbox_id or None,
                    "drain": drain,
                    "processed_trade_dates": [d["trade_date"] for d in day_summaries],
                    "days": day_summaries,
                    "finish": finish_payload,
                    "github_run_id": github_run_id,
                    "github_actor": args.github_actor,
                    "wall_time_ms": wall_ms,
                    "code_concurrency": _code_concurrency(),
                    "layer1_hoisted": layer1_hoisted,
                    "writer_workflow": writer_workflow,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except FencingMismatch as exc:
        req = _load_request(adapter, args.request_id)
        outbox_rows = _list_outbox_for_request(adapter, args.request_id)
        print(
            json.dumps(
                _skip_owned_elsewhere_payload(
                    request_id=args.request_id,
                    request_status=str(req.get("status") or ""),
                    outbox_rows=outbox_rows,
                    detail=f"fencing_mismatch:{exc}",
                ),
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        if outbox_id:
            try:
                _rpc(
                    adapter,
                    "fail_mnc_outbox",
                    {
                        "p_outbox_id": outbox_id,
                        "p_fencing_token": fencing_int,
                        "p_error": str(exc)[:2000],
                        "p_retry_seconds": 300,
                    },
                )
            except Exception as fail_exc:
                print(f"warning: fail_mnc_outbox also failed: {fail_exc}", file=sys.stderr)
        print(
            json.dumps(
                {"status": "error", "request_id": args.request_id, "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


def cmd_drain_request(args: argparse.Namespace) -> int:
    """Claim outbox for request_id (if needed) and run-request --drain."""
    ensure_seed_catalog_or_block()
    adapter = _adapter()
    request_id = str(args.request_id or "").strip()
    github_run_id = int(args.github_run_id or 0)
    claimed_by = (
        str(args.claimed_by or "").strip()
        or f"monthly-series-seed:{github_run_id or 'local'}"
    )
    outbox_id = str(args.outbox_id or "").strip()
    fencing_token = str(args.fencing_token or "").strip()
    writer_workflow = str(args.writer_workflow or "monthly.yml").strip() or "monthly.yml"

    if not outbox_id or not fencing_token:
        claimed = _claim_outbox_for_request(
            adapter,
            request_id=request_id,
            claimed_by=claimed_by,
            visibility_seconds=DRAIN_VISIBILITY_SECONDS,
        )
        if claimed is None:
            req = _load_request(adapter, request_id)
            status = str(req.get("status") or "")
            outbox_rows = _list_outbox_for_request(adapter, request_id)
            if status in _TERMINAL_SKIP_REQUEST_STATUSES:
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "skipped": True,
                            "reason": "no_pending_outbox",
                            "request_status": status,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            foreign = _foreign_active_outbox(outbox_rows, claimed_by=claimed_by)
            if foreign:
                print(
                    json.dumps(
                        _skip_owned_elsewhere_payload(
                            request_id=request_id,
                            request_status=status,
                            outbox_rows=outbox_rows,
                            detail="poller_or_other_worker_owns_outbox",
                        ),
                        ensure_ascii=False,
                    )
                )
                return 0
            # dispatch_pending + pending with empty claim is a hard failure (not skip).
            print(
                json.dumps(
                    {
                        "status": "error",
                        "reason": "no_claimable_outbox",
                        "request_id": request_id,
                        "request_status": status,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        outbox_id, fencing_int = claimed
        fencing_token = str(fencing_int)
    else:
        fencing_int = int(fencing_token)

    mark = _rpc(
        adapter,
        "mark_mnc_outbox_dispatched",
        {
            "p_outbox_id": outbox_id,
            "p_fencing_token": fencing_int,
            "p_github_run_id": github_run_id,
        },
    )
    if mark.get("ok") is False and str(mark.get("reason") or "") == "fencing_mismatch":
        req = _load_request(adapter, request_id)
        outbox_rows = _list_outbox_for_request(adapter, request_id)
        print(
            json.dumps(
                _skip_owned_elsewhere_payload(
                    request_id=request_id,
                    request_status=str(req.get("status") or ""),
                    outbox_rows=outbox_rows,
                    detail="mark_dispatched_fencing_mismatch",
                ),
                ensure_ascii=False,
            )
        )
        return 0
    _require_ok(mark, action="mark_mnc_outbox_dispatched")

    ns = argparse.Namespace(
        request_id=request_id,
        outbox_id=outbox_id,
        fencing_token=fencing_token,
        github_run_id=str(github_run_id),
        github_actor=str(args.github_actor or ""),
        drain=True,
        writer_workflow=writer_workflow,
    )
    rc = cmd_run_request(ns)
    if rc != 0:
        return rc

    while True:
        req = _load_request(adapter, request_id)
        status = str(req.get("status") or "")
        if status in _TERMINAL_SKIP_REQUEST_STATUSES:
            break
        claimed = _claim_outbox_for_request(
            adapter,
            request_id=request_id,
            claimed_by=claimed_by,
            visibility_seconds=DRAIN_VISIBILITY_SECONDS,
        )
        if claimed is None:
            outbox_rows = _list_outbox_for_request(adapter, request_id)
            foreign = _foreign_active_outbox(outbox_rows, claimed_by=claimed_by)
            if foreign:
                print(
                    json.dumps(
                        _skip_owned_elsewhere_payload(
                            request_id=request_id,
                            request_status=status,
                            outbox_rows=outbox_rows,
                            detail="followup_chunk_owned_elsewhere",
                        ),
                        ensure_ascii=False,
                    )
                )
                break
            leftover = [
                o
                for o in outbox_rows
                if str(o.get("status") or "") in {"pending", "failed"}
            ]
            if leftover:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "reason": "no_claimable_outbox",
                            "request_id": request_id,
                            "request_status": status,
                            "detail": "followup_chunk_unclaimable",
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 2
            break
        next_id, next_fencing = claimed
        mark = _rpc(
            adapter,
            "mark_mnc_outbox_dispatched",
            {
                "p_outbox_id": next_id,
                "p_fencing_token": next_fencing,
                "p_github_run_id": github_run_id,
            },
        )
        if mark.get("ok") is False and str(mark.get("reason") or "") == "fencing_mismatch":
            outbox_rows = _list_outbox_for_request(adapter, request_id)
            print(
                json.dumps(
                    _skip_owned_elsewhere_payload(
                        request_id=request_id,
                        request_status=status,
                        outbox_rows=outbox_rows,
                        detail="followup_mark_dispatched_fencing_mismatch",
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if mark.get("ok") is False:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "reason": "followup_mark_dispatched_failed",
                        "request_id": request_id,
                        "outbox_id": next_id,
                        "mark": mark,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        ns = argparse.Namespace(
            request_id=request_id,
            outbox_id=next_id,
            fencing_token=str(next_fencing),
            github_run_id=str(github_run_id),
            github_actor=str(args.github_actor or ""),
            drain=True,
            writer_workflow=writer_workflow,
        )
        rc = cmd_run_request(ns)
        if rc != 0:
            return rc
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MNC series_seed worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run-request")
    p.add_argument("--request-id", required=True)
    p.add_argument("--outbox-id", default="")
    p.add_argument("--fencing-token", default="")
    p.add_argument("--github-run-id", default="0")
    p.add_argument("--github-actor", default="")
    p.add_argument(
        "--drain",
        action="store_true",
        help="Process all remaining trade_dates in this invocation (monthly inline).",
    )
    p.add_argument("--writer-workflow", default="monthly_new_core_backfill.yml")
    p.set_defaults(func=cmd_run_request)

    d = sub.add_parser(
        "drain-request",
        help="Claim outbox for request_id and drain all remaining trade_dates.",
    )
    d.add_argument("--request-id", required=True)
    d.add_argument("--outbox-id", default="")
    d.add_argument("--fencing-token", default="")
    d.add_argument("--github-run-id", default="0")
    d.add_argument("--github-actor", default="")
    d.add_argument("--claimed-by", default="")
    d.add_argument("--writer-workflow", default="monthly.yml")
    d.set_defaults(func=cmd_drain_request)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
