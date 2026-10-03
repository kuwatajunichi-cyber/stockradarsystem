"""Assemble and optionally commit Track D web-asof bundles from live caches.

Fake generation stores are forbidden on the live --put path.
Does not CAS metric_set_v1_1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.storage.r2_client import _load_dotenv  # noqa: E402
from scripts.storage.r2_staging_client import R2StagingAdapter  # noqa: E402
from stockradar.config import (  # noqa: E402
    get_index_store_archive_zip_path,
    get_yf_daily_cache_dir,
    get_yf_index_cache_dir,
)
from stockradar.jobs.assemble_web_asof import (  # noqa: E402
    AssembleWebAsofError,
    extract_zip,
    payloads_from_freeze_sqlite,
    write_payload_files,
)
from stockradar.jobs.write_web_asof_bundle import (  # noqa: E402
    WEB_ASOF_SOURCE_WORKFLOW,
    WebAsofGenerationRequest,
    run_web_asof_generation,
)
from stockradar.prototype_web_ui_asof.freeze_core import FreezePaths, freeze_asof  # noqa: E402
from stockradar.storage.derived_adapters import (  # noqa: E402
    generation_store_from_env,
    is_derived_generation_fake,
    r2_store_from_env,
    registry_store_from_env,
)
from stockradar.storage.mapping_catalog import get_entry, web_asof_writer_enabled  # noqa: E402
from stockradar.storage.supabase_client import (  # noqa: E402
    ENV_SUPABASE_SECRET_KEY,
    ENV_SUPABASE_URL,
    SupabaseRestAdapter,
)

_load_dotenv()


def _emit(payload: dict, json_output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(text + "\n", encoding="utf-8")


def _adapter_supabase() -> SupabaseRestAdapter:
    url = os.environ.get(ENV_SUPABASE_URL, "").strip()
    key = os.environ.get(ENV_SUPABASE_SECRET_KEY, "").strip()
    if not url or not key:
        raise AssembleWebAsofError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    return SupabaseRestAdapter.from_env()


def _download_cache_zip(supabase: SupabaseRestAdapter, r2: R2StagingAdapter, entry_id: str, dest: Path) -> str:
    cache_key = str(get_entry(entry_id)["source_name_pattern"])
    pointer = supabase.get_cache_pointer(cache_key=cache_key)
    if pointer is None:
        raise AssembleWebAsofError(f"cache pointer missing: {cache_key}")
    object_key = str(pointer["object_key"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r2.get_object(object_key))
    return object_key


def _download_enriched_csv(supabase: SupabaseRestAdapter, r2: R2StagingAdapter, as_of: str, dest: Path) -> str:
    compact = as_of.replace("-", "")
    needle = f"indicators_event_enriched_{compact}.csv"
    resp = supabase._request(
        "GET",
        "/rest/v1/artifact_index",
        params={
            "object_key": f"like.*{needle}",
            "status": "eq.committed",
            "select": "object_key,committed_at_utc,size_bytes",
            "order": "committed_at_utc.desc",
            "limit": "1",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        raise AssembleWebAsofError(f"committed enriched CSV missing for {as_of}")
    object_key = str(rows[0]["object_key"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_bytes(r2.get_object(object_key))
    except Exception as exc:
        if type(exc).__name__ != "NoSuchKey" and "NoSuchKey" not in str(exc):
            raise
        raise AssembleWebAsofError(
            f"r2_csv_nosuchkey as_of={as_of} object_key={object_key}"
        ) from exc
    return object_key


def _resolve_active_set() -> tuple[str, str]:
    registry = registry_store_from_env()
    set_id = registry.get_active_metric_set_id()
    if not set_id:
        raise AssembleWebAsofError("active metric set missing")
    row = registry.get_metric_set_version(set_id)
    if not row:
        raise AssembleWebAsofError(f"metric_set_versions row missing: {set_id}")
    fingerprint = str(row.get("set_fingerprint") or "").strip().lower()
    if len(fingerprint) != 64:
        raise AssembleWebAsofError("active set_fingerprint must be 64 hex chars")
    return str(row["id"]).strip().lower(), fingerprint


def cmd_assemble(args: argparse.Namespace) -> int:
    if args.require_enabled and not web_asof_writer_enabled():
        _emit({"status": "skipped", "reason": "web_asof_writer_enabled=false"}, args.json_output)
        return 0
    if args.put and is_derived_generation_fake():
        print("error: Fake generation stores are forbidden on the live path", file=sys.stderr)
        return 2

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    as_of = args.as_of
    date.fromisoformat(as_of)

    ohlc_zip = work / "ohlc_store.zip"
    index_zip = work / "index_store.zip"
    csv_path = work / "enriched.csv"
    sqlite_path = work / "freeze.sqlite"
    payload_dir = work / "payloads"

    downloaded: dict[str, str] = {}
    if not args.skip_download:
        supabase = _adapter_supabase()
        r2 = R2StagingAdapter()
        downloaded["ohlc"] = _download_cache_zip(
            supabase, r2, "cache-ohlc-store-zip-v2", ohlc_zip
        )
        downloaded["index"] = _download_cache_zip(
            supabase, r2, "cache-index-store-zip-v1", index_zip
        )
        downloaded["csv"] = _download_enriched_csv(supabase, r2, as_of, csv_path)

    if not csv_path.is_file():
        raise AssembleWebAsofError(f"enriched csv missing: {csv_path}")

    daily_dir = get_yf_daily_cache_dir(work)
    index_dir = get_yf_index_cache_dir(work)
    if not args.skip_download or not daily_dir.exists():
        archive_dir = work / "data" / "cache" / "ohlc_store_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        staged_ohlc = archive_dir / "ohlc_store.zip"
        if ohlc_zip.resolve() != staged_ohlc.resolve():
            staged_ohlc.write_bytes(ohlc_zip.read_bytes())
        extract_zip(staged_ohlc, daily_dir)
        staged_index = get_index_store_archive_zip_path(work)
        staged_index.parent.mkdir(parents=True, exist_ok=True)
        if index_zip.resolve() != staged_index.resolve():
            staged_index.write_bytes(index_zip.read_bytes())
        extract_zip(staged_index, index_dir)

    codes = [c.strip().zfill(4) for c in (args.codes or "").split(",") if c.strip()] or None
    if args.skip_freeze:
        if not sqlite_path.is_file():
            raise AssembleWebAsofError(f"freeze sqlite missing: {sqlite_path}")
        freeze_meta = {"skipped": True, "sqlite": str(sqlite_path)}
    else:
        freeze_meta = freeze_asof(
            FreezePaths(
                csv_path=csv_path,
                daily_cache_dir=daily_dir,
                index_cache_dir=index_dir,
                out_sqlite=sqlite_path,
            ),
            as_of=date.fromisoformat(as_of),
            codes=codes,
            exclude_stale_symbols=True,
            overwrite_metrics_from_cache=True,
        )

    set_id, fingerprint = _resolve_active_set()
    payloads = payloads_from_freeze_sqlite(
        sqlite_path,
        metric_set_version_id=set_id,
        set_fingerprint=fingerprint,
    )
    paths = write_payload_files(payloads, payload_dir)
    result_payload: dict = {
        "status": "assembled",
        "as_of": as_of,
        "metric_set_version_id": set_id,
        "set_fingerprint": fingerprint,
        "freeze": freeze_meta,
        "payload_paths": {k: str(v) for k, v in paths.items()},
        "downloaded": downloaded,
        "skipped": False,
        "generation_id": None,
        "object_keys": [],
        "exit_code": 0,
    }
    if args.put:
        result = run_web_asof_generation(
            WebAsofGenerationRequest(
                as_of=as_of,
                metric_set_version_id=set_id,
                set_fingerprint=fingerprint,
                repository=args.repository,
                github_run_id=int(args.github_run_id),
                workflow=args.workflow,
                payloads=payloads,
            ),
            generation_store=generation_store_from_env(),
            r2_store=r2_store_from_env(),
        )
        result_payload.update(
            {
                "status": result.status,
                "exit_code": result.exit_code,
                "generation_id": result.generation_id,
                "reason": result.reason,
                "object_keys": list(result.object_keys),
                "skipped": result.skipped,
            }
        )
        _emit(result_payload, args.json_output)
        return int(result.exit_code)
    _emit(result_payload, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble Track D web-asof bundles.")
    sub = parser.add_subparsers(dest="command", required=True)
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--as-of", required=True)
    assemble.add_argument("--work-dir", required=True, type=Path)
    assemble.add_argument("--github-run-id", type=int, default=1)
    assemble.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "local"))
    assemble.add_argument("--workflow", default=WEB_ASOF_SOURCE_WORKFLOW)
    assemble.add_argument("--codes", default="")
    assemble.add_argument("--put", action="store_true")
    assemble.add_argument("--require-enabled", action="store_true")
    assemble.add_argument("--skip-download", action="store_true")
    assemble.add_argument("--skip-freeze", action="store_true")
    assemble.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command != "assemble":
        raise SystemExit(2)
    try:
        return cmd_assemble(args)
    except AssembleWebAsofError as exc:
        _emit({"status": "error", "reason": str(exc), "exit_code": 2}, args.json_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
