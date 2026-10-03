"""Resolve the canonical metric-set YAML from a registry UUID fingerprint.

Prod daily/backfill/reconcile must pass this path to derived_bus_cli.
Does not CAS. Fake stores are forbidden (exit 2).
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
from stockradar.metrics.catalog_bind import (  # noqa: E402
    CatalogYamlMismatchError,
    yaml_path_for_registry_row,
)
from stockradar.storage.derived_adapters import (  # noqa: E402
    is_derived_generation_fake,
    registry_store_from_env,
)

_load_dotenv()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve metric-set YAML from registry UUID.")
    parser.add_argument("--metric-set-version-id", default="")
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args(argv)
    if is_derived_generation_fake():
        payload = {
            "status": "error",
            "exit_code": 2,
            "reason": "fake_registry_forbidden",
        }
        text = json.dumps(payload, ensure_ascii=False)
        print(text, file=sys.stderr)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 2
    registry = registry_store_from_env()
    set_id = str(args.metric_set_version_id or "").strip()
    if not set_id:
        set_id = str(registry.get_active_metric_set_id() or "").strip()
    if not set_id:
        payload = {
            "status": "error",
            "exit_code": 2,
            "reason": "active_metric_set_missing",
        }
        text = json.dumps(payload, ensure_ascii=False)
        print(text, file=sys.stderr)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 2
    row = registry.get_metric_set_version(set_id)
    if row is None:
        payload = {
            "status": "error",
            "exit_code": 2,
            "reason": "unknown_metric_set_version",
            "metric_set_version_id": set_id,
        }
        text = json.dumps(payload, ensure_ascii=False)
        print(text, file=sys.stderr)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 2
    try:
        yaml_path = yaml_path_for_registry_row(row)
    except CatalogYamlMismatchError as exc:
        payload = {
            "status": "error",
            "exit_code": 2,
            "reason": "metric_set_yaml_mismatch",
            "detail": str(exc),
            "metric_set_version_id": set_id,
        }
        text = json.dumps(payload, ensure_ascii=False)
        print(text, file=sys.stderr)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 2
    rel = yaml_path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    if args.json_output is not None:
        payload = {
            "status": "ok",
            "exit_code": 0,
            "metric_set_version_id": str(row["id"]).strip().lower(),
            "set_key": row.get("set_key"),
            "set_fingerprint": row.get("set_fingerprint"),
            "metric_set_yaml": rel,
        }
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
