"""Delete forbidden derived-shadow leftovers and unindexed failed-generation snapshot objects."""
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

from stockradar.storage.derived_leftover import leftover_scan_prefixes  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List leftover derived R2 prefixes (dry-run default).")
    parser.add_argument("--metric-set-version-id")
    parser.add_argument("--trade-date")
    parser.add_argument("--generation-id")
    parser.add_argument("--include-forbidden", action="store_true", default=True)
    parser.add_argument("--json-output")
    args = parser.parse_args(argv)
    prefixes = leftover_scan_prefixes(
        metric_set_version_id=args.metric_set_version_id,
        trade_date=args.trade_date,
        generation_id=args.generation_id,
        include_forbidden=args.include_forbidden,
    )
    payload = {"status": "ok", "dry_run": True, "prefixes": prefixes}
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
