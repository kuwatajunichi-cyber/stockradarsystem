"""Resolve daily run terminal status for finalize_run job (Phase 4)."""
from __future__ import annotations

import argparse
import json
from stockradar.jobs.run_terminal_status import DailyRunTerminalInput, resolve_daily_run_terminal_status


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resolve daily run terminal status.")
    parser.add_argument("--is-open", required=True, choices=("true", "false", "True", "False"))
    parser.add_argument("--compute-result", default="skipped")
    parser.add_argument("--enrichment-result", default="skipped")
    parser.add_argument("--render-result", default="skipped")
    parser.add_argument("--skip-publish", default="false")
    parser.add_argument("--upload-executed", default="false")
    parser.add_argument("--upload-exit-code", type=int, default=0)
    parser.add_argument("--upload-status", default="ok")
    args = parser.parse_args(argv)

    is_open = args.is_open.lower() == "true"
    skip_publish = args.skip_publish.lower() in ("true", "1", "yes")
    upload_executed = args.upload_executed.lower() in ("true", "1", "yes")

    def _norm(result: str) -> str:
        r = result.strip().lower()
        if r in ("success", "failure", "skipped", "cancelled"):
            return r
        return "skipped"

    decision = resolve_daily_run_terminal_status(
        DailyRunTerminalInput(
            is_open=is_open,
            compute_indicators=_norm(args.compute_result),  # type: ignore[arg-type]
            event_cause_enrichment=_norm(args.enrichment_result),  # type: ignore[arg-type]
            render_and_upload=_norm(args.render_result),  # type: ignore[arg-type]
            skip_publish=skip_publish,
            upload_executed=upload_executed,
            upload_exit_code=args.upload_exit_code,
            upload_status=args.upload_status,
        )
    )
    payload = {"status": decision.status, "degraded_reason": decision.degraded_reason}
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
