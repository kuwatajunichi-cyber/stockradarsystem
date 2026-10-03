"""Ops CAS for metric_set_versions (Path B provenance: writer_workflow ops-activate-metric-set-cas).

Does not seed. Fake stores are forbidden. source_github_run_id 0 means local ops adapter.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.storage.r2_client import _load_dotenv  # noqa: E402
from stockradar.storage.derived_adapters import is_derived_generation_fake  # noqa: E402
from stockradar.storage.metric_registry import ActiveMetricSetCasConflictError  # noqa: E402
from stockradar.storage.supabase_metric_registry import (  # noqa: E402
    SupabaseMetricRegistryAdapter,
)

_load_dotenv()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate a shadow/retired metric set via CAS.")
    parser.add_argument("--expected-set-id", required=True)
    parser.add_argument("--new-set-id", required=True)
    parser.add_argument("--writer-workflow", default="ops-activate-metric-set-cas")
    parser.add_argument("--source-github-run-id", type=int, default=0)
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args(argv)
    if is_derived_generation_fake():
        print(
            json.dumps({"status": "error", "exit_code": 2, "reason": "fake_registry_forbidden"}),
            file=sys.stderr,
        )
        return 2
    registry = SupabaseMetricRegistryAdapter.from_env()
    expected = args.expected_set_id.strip().lower()
    new_id = args.new_set_id.strip().lower()
    before = registry.get_active_metric_set_id()
    try:
        registry.activate_metric_set_cas(
            expected_set_id=expected,
            new_set_id=new_id,
            writer_workflow=args.writer_workflow,
            source_github_run_id=int(args.source_github_run_id),
        )
    except ActiveMetricSetCasConflictError as exc:
        payload = {
            "status": "error",
            "exit_code": 2,
            "reason": "active_metric_set_cas_conflict",
            "detail": str(exc),
            "active_before": before,
        }
        text = json.dumps(payload, ensure_ascii=False)
        print(text, file=sys.stderr)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 2
    after = registry.get_active_metric_set_id()
    new_row = registry.get_metric_set_version(new_id)
    old_row = registry.get_metric_set_version(expected)
    payload = {
        "status": "ok",
        "exit_code": 0,
        "operation": "activate_metric_set_cas",
        "expected_set_id": expected,
        "new_set_id": new_id,
        "writer_workflow": args.writer_workflow,
        "source_github_run_id": int(args.source_github_run_id),
        "active_before": before,
        "active_after": after,
        "new_set_lifecycle_after": None if new_row is None else new_row.get("lifecycle_status"),
        "old_set_lifecycle_after": None if old_row is None else old_row.get("lifecycle_status"),
        "new_set_key": None if new_row is None else new_row.get("set_key"),
        "new_set_fingerprint": None if new_row is None else new_row.get("set_fingerprint"),
    }
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
