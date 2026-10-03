"""Web-asof bundle bus CLI (Track D). Fake via DERIVED_GENERATION_FAKE."""
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

from stockradar.jobs.write_web_asof_bundle import (  # noqa: E402
    WEB_ASOF_SOURCE_WORKFLOW,
    WebAsofGenerationRequest,
    run_web_asof_generation,
)
from stockradar.storage.derived_adapters import (  # noqa: E402
    generation_store_from_env,
    r2_store_from_env,
)
from stockradar.storage.mapping_catalog import web_asof_writer_enabled  # noqa: E402


def _load_payload(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"payload must be an object: {path}")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Track D web-asof bundles.")
    sub = parser.add_subparsers(dest="command", required=True)
    put = sub.add_parser("put-generation")
    put.add_argument("--as-of", required=True)
    put.add_argument("--metric-set-version-id", required=True)
    put.add_argument("--set-fingerprint", required=True)
    put.add_argument("--payload-topix", required=True, type=Path)
    put.add_argument("--payload-nikkei", required=True, type=Path)
    put.add_argument("--repository", default="local")
    put.add_argument("--github-run-id", type=int, default=1)
    put.add_argument("--workflow", default=WEB_ASOF_SOURCE_WORKFLOW)
    put.add_argument("--json-output", type=Path, default=None)
    put.add_argument("--require-enabled", action="store_true")
    args = parser.parse_args(argv)

    if args.command != "put-generation":
        raise SystemExit(2)
    if args.require_enabled and not web_asof_writer_enabled():
        payload = {"status": "skipped", "reason": "web_asof_writer_enabled=false"}
        text = json.dumps(payload, ensure_ascii=False)
        print(text)
        if args.json_output is not None:
            args.json_output.write_text(text, encoding="utf-8")
        return 0

    result = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=args.as_of,
            metric_set_version_id=args.metric_set_version_id,
            set_fingerprint=args.set_fingerprint,
            repository=args.repository,
            github_run_id=int(args.github_run_id),
            workflow=args.workflow,
            payloads={
                "topix": _load_payload(args.payload_topix),
                "nikkei": _load_payload(args.payload_nikkei),
            },
        ),
        generation_store=generation_store_from_env(),
        r2_store=r2_store_from_env(),
    )
    payload = {
        "status": result.status,
        "exit_code": result.exit_code,
        "generation_id": result.generation_id,
        "reason": result.reason,
        "object_keys": list(result.object_keys),
        "skipped": result.skipped,
    }
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if args.json_output is not None:
        args.json_output.write_text(text, encoding="utf-8")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
