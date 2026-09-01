"""ADR-005 worker: series_seed chunk (heartbeat → write ≤10 trade_dates → finish)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

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


class FencingMismatch(Exception):
    """Outbox fencing token no longer owned by this worker."""


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
    if isinstance(payload, dict):
        return payload
    return {"ok": True, "result": payload}


def _fake_rpc(adapter: FakeSupabaseControlAdapter, name: str, body: dict[str, Any]) -> dict[str, Any]:
    outbox_id = str(body.get("p_outbox_id") or "")
    fencing = int(body.get("p_fencing_token") or 0)
    row = next((o for o in adapter.mnc_outbox if str(o.get("id")) == outbox_id), None)
    if name == "heartbeat_mnc_outbox":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        row["heartbeat_at"] = "fake-ts"
        return {"ok": True, "outbox_id": outbox_id}
    if name == "fail_mnc_outbox":
        if row is None:
            return {"ok": False, "reason": "not_found"}
        if int(row.get("fencing_token") or 0) != fencing:
            return {"ok": False, "reason": "fencing_mismatch"}
        row["status"] = "failed"
        row["last_error"] = str(body.get("p_error") or "worker_failed")[:2000]
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

    daily_manifest_path = daily_dir / MANIFEST_FILENAME
    daily_manifest = load_manifest(daily_manifest_path)
    for code in codes:
        ticker = ticker_for_code(code)
        ent = ensure_cache_with_incremental_fetch(
            symbol=code,
            ticker=ticker,
            cache_path=daily_dir / f"{code}.csv",
            manifest=daily_manifest,
            required_days=required_days,
            run_date=trade_date,
        )
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
    for code in codes:
        result = _compute_one_code((code, ""))
        status = str(result.get("status") or "")
        if status == "missing":
            raise RuntimeError(f"ohlcv missing for code={code} trade_date={trade_date}")
        if status == "stale_ohlc":
            raise RuntimeError(f"ohlcv stale for code={code} trade_date={trade_date}")
        row = dict(result.get("row") or {})
        values[code] = _row_to_metric_values(row, metric_keys_ordered)
    return values


def cmd_run_request(args: argparse.Namespace) -> int:
    ensure_seed_catalog_or_block()
    adapter = _adapter()
    outbox_id = str(args.outbox_id or "").strip()
    fencing_token = str(args.fencing_token or "").strip()
    github_run_id = int(args.github_run_id or 0)
    repository = os.environ.get("GITHUB_REPOSITORY", "local/stockradarsystem").strip()

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
                "p_visibility_seconds": DEFAULT_VISIBILITY_SECONDS,
            },
        )
        _require_ok(payload, action="heartbeat_mnc_outbox")

    try:
        heartbeat()
        req = _load_request(adapter, args.request_id)
        status = str(req.get("status") or "")
        if status in {
            "completed",
            "noop",
            "blocked",
            "grandfather",
            "superseded",
            "paused",
        }:
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

        chunk = remaining[:MAX_TRADE_DATES_PER_CHUNK]
        metric_set_version_id = (
            os.environ.get("ADR005_METRIC_SET_VERSION_ID", "").strip()
            or "00000000-0000-0000-0000-000000000001"
        )
        spec = load_metric_set_spec()
        metric_keys = spec.metric_keys_ordered
        generation_store = generation_store_from_env()
        r2_store = r2_store_from_env()

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

        day_summaries: list[dict[str, Any]] = []
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
                )
                # Refresh in-memory state for subsequent days in this chunk.
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

        finish_payload: dict[str, Any] | None = None
        if outbox_id:
            finish_payload = _rpc(
                adapter,
                "finish_mnc_outbox_chunk",
                {"p_outbox_id": outbox_id, "p_fencing_token": fencing_int},
            )
            _require_ok(finish_payload, action="finish_mnc_outbox_chunk")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "request_id": args.request_id,
                    "outbox_id": outbox_id or None,
                    "processed_trade_dates": [d["trade_date"] for d in day_summaries],
                    "days": day_summaries,
                    "finish": finish_payload,
                    "github_run_id": github_run_id,
                    "github_actor": args.github_actor,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except FencingMismatch as exc:
        print(
            json.dumps(
                {"status": "ok", "skipped": True, "reason": "fencing_mismatch", "detail": str(exc)},
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MNC series_seed worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run-request")
    p.add_argument("--request-id", required=True)
    p.add_argument("--outbox-id", default="")
    p.add_argument("--fencing-token", default="")
    p.add_argument("--github-run-id", default="0")
    p.add_argument("--github-actor", default="")
    p.set_defaults(func=cmd_run_request)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
