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


def main() -> int:
    import os

    _load_dotenv()

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SECRET_KEY"):
        return _fail("SUPABASE_URL and SUPABASE_SECRET_KEY required")

    adapter = SupabaseRestAdapter.from_env()
    artifact_id: str | None = None
    cache_history_id: str | None = None
    smoke_github_run_id = int(os.environ.get("GITHUB_RUN_ID") or "0")

    try:
        run = adapter.upsert_run(
            workflow=SMOKE_WORKFLOW,
            github_run_id=smoke_github_run_id,
            run_date="2026-01-01",
        )
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

        print("smoke ok: upsert-run, artifact_index REST, commit_fixed_cache RPC")
        return 0
    except Exception as exc:
        return _fail(str(exc))
    finally:
        if artifact_id:
            try:
                adapter.delete_row(table="artifact_index", row_id=artifact_id)
            except Exception:
                pass
        if cache_history_id:
            try:
                adapter.delete_row(table="cache_index", row_id=cache_history_id)
            except Exception:
                pass
        try:
            _delete_cache_pointer(adapter, SMOKE_CACHE_KEY)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
