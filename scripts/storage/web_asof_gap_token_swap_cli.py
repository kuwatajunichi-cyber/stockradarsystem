"""Rewrite stored GAP tokens in committed web-asof bundles.

Fake generation stores are forbidden on --put.
Does not CAS. Phase 5 stays in_progress.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.storage.r2_client import _load_dotenv  # noqa: E402
from stockradar.config import get_yf_daily_cache_dir  # noqa: E402
from stockradar.jobs.swap_web_asof_gap_tokens import (  # noqa: E402
    commit_swapped_as_of,
    generation_result_as_dict,
    load_and_swap,
)
from stockradar.storage.derived_adapters import (  # noqa: E402
    generation_store_from_env,
    is_derived_generation_fake,
    r2_store_from_env,
    registry_store_from_env,
)
from stockradar.storage.supabase_client import (  # noqa: E402
    ENV_SUPABASE_SECRET_KEY,
    ENV_SUPABASE_URL,
    SupabaseRestAdapter,
)
from stockradar.storage.web_asof_bundle import gunzip_bundle_bytes  # noqa: E402
from stockradar.storage.web_asof_gap_token_swap import (  # noqa: E402
    GAP_DOWN,
    GAP_UP,
    GENERATOR_FIX_COMMITTED_AT_UTC,
    SWAP_MODE,
    SWAP_REPOSITORY,
    SWAP_WORKFLOW,
    BundlePointer,
    GapTokenSwapError,
    label_tokens,
    latest_pre_cutoff_pointers,
    pair_as_of_pointers,
    sakata_gap_token,
    swap_github_run_id,
)

_load_dotenv()


def _emit(payload: dict[str, Any], json_output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(text + "\n", encoding="utf-8")


def _supabase() -> SupabaseRestAdapter:
    import os

    url = os.environ.get(ENV_SUPABASE_URL, "").strip()
    key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    return SupabaseRestAdapter.from_env()


def _active_set_id() -> str:
    registry = registry_store_from_env()
    set_id = registry.get_active_metric_set_id()
    if not set_id:
        raise RuntimeError("active metric set missing")
    return set_id


def _list_committed_bundle_rows(client: SupabaseRestAdapter, set_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page = 1000
    while True:
        resp = client._request(
            "GET",
            "/rest/v1/derived_object_index",
            params={
                "object_kind": "eq.web_asof_bundle",
                "status": "eq.committed",
                "metric_set_version_id": f"eq.{set_id}",
                "select": "trade_date,benchmark,object_key,byte_sha256,committed_at_utc",
                "order": "committed_at_utc.desc",
                "limit": str(page),
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        chunk = resp.json()
        if not isinstance(chunk, list) or not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    return rows


def _identity_status(client: SupabaseRestAdapter, *, set_id: str, as_of: str) -> str | None:
    resp = client._request(
        "GET",
        "/rest/v1/derived_generation_runs",
        params={
            "workflow": f"eq.{SWAP_WORKFLOW}",
            "mode": f"eq.{SWAP_MODE}",
            "repository": f"eq.{SWAP_REPOSITORY}",
            "metric_set_version_id": f"eq.{set_id}",
            "trade_date": f"eq.{as_of}",
            "github_run_id": f"eq.{swap_github_run_id(as_of)}",
            "select": "id,status,committed_at_utc",
            "order": "created_at_utc.desc",
            "limit": "1",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return None
    return str(rows[0].get("status") or "") or None


def _worklist(client: SupabaseRestAdapter, set_id: str) -> dict[str, Any]:
    raw = _list_committed_bundle_rows(client, set_id)
    pointers = latest_pre_cutoff_pointers(raw, cutoff=GENERATOR_FIX_COMMITTED_AT_UTC)
    pairs, missing = pair_as_of_pointers(pointers)
    return {
        "metric_set_version_id": set_id,
        "cutoff": GENERATOR_FIX_COMMITTED_AT_UTC.isoformat(),
        "committed_rows": len(raw),
        "pre_cutoff_pointers": len(pointers),
        "as_of_count": len(pairs),
        "as_of_dates": [item[0] for item in pairs],
        "missing_benchmark": missing,
        "pairs": pairs,
    }


def _inspect_pairs(
    r2,
    pairs: list[tuple[str, BundlePointer, BundlePointer]],
) -> dict[str, Any]:
    gap_token_rows = 0
    gap_phrase_rows = 0
    failures: list[dict[str, str]] = []
    for as_of, topix, nikkei in pairs:
        for pointer in (topix, nikkei):
            try:
                _payload, stats = load_and_swap(r2, pointer)
            except (GapTokenSwapError, ValueError, OSError, KeyError) as exc:
                failures.append(
                    {
                        "as_of": as_of,
                        "benchmark": pointer.benchmark,
                        "object_key": pointer.object_key,
                        "error": str(exc),
                    }
                )
                continue
            gap_token_rows += stats.rows_with_gap_token
            gap_phrase_rows += stats.rows_with_gap_phrase
    return {
        "gap_token_rows": gap_token_rows,
        "gap_phrase_rows": gap_phrase_rows,
        "validation_failures": failures,
    }


def _parse_ohlc_day(raw: str) -> date | None:
    text = str(raw).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _ohlc_bars(path: Path) -> list[tuple[date, float, float]]:
    rows: list[tuple[date, float, float]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            day = _parse_ohlc_day(str(row.get("Date") or row.get("date") or ""))
            if day is None:
                continue
            try:
                high = float(row["High"] if "High" in row else row["high"])
                low = float(row["Low"] if "Low" in row else row["low"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append((day, high, low))
    rows.sort(key=lambda item: item[0])
    return rows


def _spot_from_payload(payload: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    as_of = str(payload.get("as_of") or "")
    as_of_day = date.fromisoformat(as_of)
    skipped: list[dict[str, str]] = []
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        tokens = label_tokens(str(row.get("candle_labels") or ""))
        if GAP_DOWN not in tokens:
            continue
        code = str(row.get("code") or "")
        csv_path = cache_dir / f"{code}.csv"
        spot: dict[str, Any] = {
            "as_of": as_of,
            "code": code,
            "stored_labels": row.get("candle_labels"),
            "stored_price_text": row.get("price_text"),
            "ohlc_path": str(csv_path),
        }
        if not csv_path.is_file():
            skipped.append({"code": code, "ohlc": "missing"})
            continue
        bars = _ohlc_bars(csv_path)
        today = next((item for item in bars if item[0] == as_of_day), None)
        prev_candidates = [item for item in bars if item[0] < as_of_day]
        if today is None or not prev_candidates:
            skipped.append({"code": code, "ohlc": "as_of_or_prev_missing"})
            continue
        prev = prev_candidates[-1]
        expected = sakata_gap_token(
            prev_high=prev[1],
            prev_low=prev[2],
            today_high=today[1],
            today_low=today[2],
        )
        spot["ohlc"] = {
            "prev_date": prev[0].isoformat(),
            "prev_high": prev[1],
            "prev_low": prev[2],
            "today_high": today[1],
            "today_low": today[2],
            "sakata_token": expected,
            "stored_is_old_mapping": expected == GAP_UP and GAP_DOWN in tokens,
        }
        if skipped:
            spot["skipped"] = skipped[:5]
        return spot
    return {"as_of": as_of, "reason": "no_confirmable_GAP_DOWN_row", "skipped": skipped[:8]}


def cmd_dry_run(args: argparse.Namespace) -> int:
    client = _supabase()
    set_id = _active_set_id()
    work = _worklist(client, set_id)
    r2 = r2_store_from_env()
    inspected = _inspect_pairs(r2, work["pairs"])
    payload = {
        "status": "error" if inspected["validation_failures"] or work["missing_benchmark"] else "ok",
        "metric_set_version_id": set_id,
        "cutoff": work["cutoff"],
        "committed_rows": work["committed_rows"],
        "as_of_count": work["as_of_count"],
        "as_of_dates": work["as_of_dates"],
        "missing_benchmark": work["missing_benchmark"],
        "gap_token_rows": inspected["gap_token_rows"],
        "gap_phrase_rows": inspected["gap_phrase_rows"],
        "validation_failures": inspected["validation_failures"],
        "swap_workflow": SWAP_WORKFLOW,
    }
    _emit(payload, args.json_output)
    return 1 if payload["status"] != "ok" else 0


def cmd_spot_check(args: argparse.Namespace) -> int:
    client = _supabase()
    set_id = _active_set_id()
    work = _worklist(client, set_id)
    if not work["pairs"]:
        _emit({"status": "error", "reason": "no_pre_cutoff_as_of"}, args.json_output)
        return 1
    as_of = args.as_of or work["as_of_dates"][-1]
    pair = next((item for item in work["pairs"] if item[0] == as_of), None)
    if pair is None:
        _emit({"status": "error", "reason": "as_of_not_in_worklist", "as_of": as_of}, args.json_output)
        return 1
    r2 = r2_store_from_env()
    blob = r2.get_object(pair[1].object_key)
    payload = gunzip_bundle_bytes(blob)
    cache_dir = get_yf_daily_cache_dir(_REPO_ROOT)
    spot = _spot_from_payload(payload, cache_dir)
    _emit({"status": "ok", "spot": spot, "cache_dir": str(cache_dir)}, args.json_output)
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    if is_derived_generation_fake():
        print("error: Fake generation stores are forbidden on the live path", file=sys.stderr)
        return 2
    client = _supabase()
    set_id = _active_set_id()
    work = _worklist(client, set_id)
    if work["missing_benchmark"]:
        _emit(
            {
                "status": "error",
                "reason": "missing_benchmark",
                "missing_benchmark": work["missing_benchmark"],
            },
            args.json_output,
        )
        return 1
    wanted = list(work["as_of_dates"])
    if args.as_of:
        date.fromisoformat(args.as_of)
        if args.as_of not in wanted:
            _emit(
                {"status": "error", "reason": "as_of_not_in_worklist", "as_of": args.as_of},
                args.json_output,
            )
            return 1
        wanted = [args.as_of]
    r2 = r2_store_from_env()
    store = generation_store_from_env()
    results: list[dict[str, Any]] = []
    for as_of, topix, nikkei in work["pairs"]:
        if as_of not in wanted:
            continue
        identity = _identity_status(client, set_id=set_id, as_of=as_of)
        try:
            result = commit_swapped_as_of(
                as_of=as_of,
                topix=topix,
                nikkei=nikkei,
                generation_store=store,
                r2_store=r2,
                existing_status=identity,
            )
        except (GapTokenSwapError, ValueError) as exc:
            payload = {
                "status": "error",
                "reason": str(exc),
                "as_of": as_of,
                "done": results,
            }
            _emit(payload, args.json_output)
            return 1
        results.append(generation_result_as_dict(result))
        print(
            f"[gap-swap] {as_of} {result.status} labels={result.topix.labels_changed}/{result.nikkei.labels_changed}",
            file=sys.stderr,
        )
        if result.status not in {"ok", "skipped"}:
            _emit(
                {
                    "status": "error",
                    "reason": result.reason,
                    "as_of": as_of,
                    "done": results,
                },
                args.json_output,
            )
            return 1
    _emit({"status": "ok", "count": len(results), "results": results}, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Swap stored GAP_UP/GAP_DOWN in web-asof bundles.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dry = sub.add_parser("dry-run")
    dry.add_argument("--json-output", type=Path, default=None)
    dry.set_defaults(func=cmd_dry_run)
    spot = sub.add_parser("spot-check")
    spot.add_argument("--as-of", default=None)
    spot.add_argument("--json-output", type=Path, default=None)
    spot.set_defaults(func=cmd_spot_check)
    commit = sub.add_parser("commit")
    commit.add_argument("--as-of", default=None, help="One as-of. Omit to rewrite the whole worklist.")
    commit.add_argument("--json-output", type=Path, default=None)
    commit.set_defaults(func=cmd_commit)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
