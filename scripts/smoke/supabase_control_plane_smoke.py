"""Supabase control plane smoke (Secrets required).

Runnable locally (.env) or from .github/workflows/supabase_smoketest.yml.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from stockradar.storage.supabase_client import SupabaseRestAdapter  # noqa: E402

SMOKE_WORKFLOW = "supabase_smoketest.yml"
SMOKE_CACHE_KEY = "smoke-index-store-zip-v1"
SMOKE_SHA = "a" * 64
SMOKE_JPX_CACHE_KEY = "smoke-jpx-latest-url"




def _load_dotenv() -> None:
    import os

    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

def _fail(msg: str) -> int:
    print(f"smoke failed: {msg}", file=sys.stderr)
    return 1


def _delete_cache_pointer(adapter: SupabaseRestAdapter, cache_key: str) -> None:
    resp = adapter._request(
        "DELETE",
        "/rest/v1/cache_pointers",
        params={"cache_key": f"eq.{cache_key}"},
    )
    resp.raise_for_status()


def _delete_run_row(
    adapter: SupabaseRestAdapter,
    *,
    workflow: str,
    github_run_id: int,
) -> None:
    resp = adapter._request(
        "DELETE",
        "/rest/v1/runs",
        params={
            "workflow": f"eq.{workflow}",
            "github_run_id": f"eq.{github_run_id}",
        },
    )
    resp.raise_for_status()


class _CleanupFailure(Exception):
    pass


def _cleanup_or_raise(label: str, action: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        raise _CleanupFailure(f"{label} {action} failed: {exc}") from exc


def main() -> int:
    import os

    _load_dotenv()

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SECRET_KEY"):
        return _fail("SUPABASE_URL and SUPABASE_SECRET_KEY required")

    adapter = SupabaseRestAdapter.from_env()
    artifact_id: str | None = None
    cache_history_id: str | None = None
    monthly_id: str | None = None
    publish_id: str | None = None
    jpx_id: str | None = None
    smoke_github_run_id = int(os.environ.get("GITHUB_RUN_ID") or "0")
    run_inserted_by_smoke = False
    cleanup_errors: list[str] = []

    try:
        run = adapter.get_run(workflow=SMOKE_WORKFLOW, github_run_id=smoke_github_run_id)
        if run is None:
            run = adapter.upsert_run(
                workflow=SMOKE_WORKFLOW,
                github_run_id=smoke_github_run_id,
                run_date="2026-01-01",
            )
            run_inserted_by_smoke = True
        got = adapter.get_run(workflow=SMOKE_WORKFLOW, github_run_id=smoke_github_run_id)
        if got is None or got.get("id") != run.get("id"):
            return _fail("upsert-run not readable")

        pending = adapter.insert_artifact_index_pending(
            run_id=str(run["id"]),
            source_name="smoke-artifact",
            object_key="runs/smoke/test.csv",
            sha256=SMOKE_SHA,
            size_bytes=1,
            content_type="text/csv",
        )
        artifact_id = str(pending["id"])
        committed = adapter.commit_artifact_index(artifact_id=artifact_id)
        if committed.get("status") != "committed":
            return _fail("artifact_index commit status")

        cache_history_id = adapter.commit_fixed_cache_rpc(
            cache_key=SMOKE_CACHE_KEY,
            object_key=f"cache/{SMOKE_CACHE_KEY}/{SMOKE_SHA}.zip",
            sha256=SMOKE_SHA,
            size_bytes=42,
            writer_workflow="smoke-test",
            source_github_run_id=smoke_github_run_id,
            history_id=None,
        )
        ptr = adapter.get_cache_pointer(cache_key=SMOKE_CACHE_KEY)
        if ptr is None or ptr.get("sha256") != SMOKE_SHA:
            return _fail("cache_pointers not readable after RPC")

        monthly_tag = "smoke-monthly-20260101-0"
        snap_pending = adapter.insert_monthly_snapshot_pending(
            monthly_tag=monthly_tag,
            snapshot_date="2026-01-01",
            github_run_id=smoke_github_run_id,
            object_keys={
                "monthly_snapshots_schema_version": 1,
                "ipo": {
                    "object_key": f"monthly/{monthly_tag}/equity_domestic_ipo_with_name.csv",
                    "sha256": SMOKE_SHA,
                    "size_bytes": 1,
                    "content_type": "text/csv",
                },
                "illiquid": {
                    "object_key": f"monthly/{monthly_tag}/equity_domestic_illiquid_with_name.csv",
                    "sha256": SMOKE_SHA,
                    "size_bytes": 1,
                    "content_type": "text/csv",
                },
                "core": {
                    "object_key": f"monthly/{monthly_tag}/equity_domestic_core_with_name.csv",
                    "sha256": SMOKE_SHA,
                    "size_bytes": 1,
                    "content_type": "text/csv",
                },
                "manifest": {
                    "object_key": f"monthly/{monthly_tag}/manifest.json",
                    "sha256": SMOKE_SHA,
                    "size_bytes": 1,
                    "content_type": "application/json",
                },
            },
            sha256=SMOKE_SHA,
        )
        monthly_id = str(snap_pending["id"])
        snap_committed = adapter.commit_monthly_snapshot(snapshot_id=monthly_id)
        if snap_committed.get("status") != "committed":
            return _fail("monthly_snapshots commit status")

        pub_pending = adapter.insert_publish_status_pending(
            run_id=str(run["id"]),
            workflow=SMOKE_WORKFLOW,
            github_run_id=smoke_github_run_id,
            run_date="2026-01-01",
            logical_kind="indicators_csv",
            visibility="work",
            object_key="published/0011_work/2026-01/2026-01-01/smoke.csv",
            manifest_object_key="published/0011_work/2026-01/2026-01-01/manifests/indicators_csv.json",
            size_bytes=1,
            sha256=SMOKE_SHA,
            content_type="text/csv",
        )
        publish_id = str(pub_pending["id"])
        pub_committed = adapter.commit_publish_status(publish_id=publish_id)
        if pub_committed.get("status") != "committed":
            return _fail("publish_status commit status")

        jpx_history = adapter.insert_cache_index_pending_fixed(
            cache_key=SMOKE_JPX_CACHE_KEY,
            object_key="cache/jpx-url/smoke_jpx_latest_url.txt",
            sha256=SMOKE_SHA,
            size_bytes=1,
            writer_workflow="smoke-test",
            source_github_run_id=smoke_github_run_id,
        )
        jpx_id = str(jpx_history["id"])
        # Do not call commit_jpx_url_cache_rpc: it hard-codes production jpx-latest-url.

        print("smoke ok: Phase 3 + Phase 4 control plane tables/RPC")
        return 0
    except Exception as exc:
        return _fail(str(exc))
    finally:
        try:
            if artifact_id:
                _cleanup_or_raise(
                    "artifact_index",
                    "delete",
                    lambda: adapter.delete_row(table="artifact_index", row_id=artifact_id),
                )
            if cache_history_id:
                _cleanup_or_raise(
                    "cache_index",
                    "delete",
                    lambda: adapter.delete_row(table="cache_index", row_id=cache_history_id),
                )
            if monthly_id:
                _cleanup_or_raise(
                    "monthly_snapshots",
                    "delete",
                    lambda: adapter.delete_row(table="monthly_snapshots", row_id=monthly_id),
                )
            if publish_id:
                _cleanup_or_raise(
                    "publish_status",
                    "delete",
                    lambda: adapter.delete_row(table="publish_status", row_id=publish_id),
                )
            if jpx_id:
                _cleanup_or_raise(
                    "cache_index",
                    "delete",
                    lambda: adapter.delete_row(table="cache_index", row_id=jpx_id),
                )
            _cleanup_or_raise(
                "cache_pointers",
                "delete",
                lambda: _delete_cache_pointer(adapter, SMOKE_CACHE_KEY),
            )
            _cleanup_or_raise(
                "cache_pointers",
                "delete",
                lambda: _delete_cache_pointer(adapter, SMOKE_JPX_CACHE_KEY),
            )
            if run_inserted_by_smoke:
                _cleanup_or_raise(
                    "runs",
                    "delete",
                    lambda: _delete_run_row(
                        adapter,
                        workflow=SMOKE_WORKFLOW,
                        github_run_id=smoke_github_run_id,
                    ),
                )
        except _CleanupFailure as exc:
            cleanup_errors.append(str(exc))

        if cleanup_errors:
            return _fail("cleanup incomplete: " + "; ".join(cleanup_errors))


if __name__ == "__main__":
    raise SystemExit(main())
