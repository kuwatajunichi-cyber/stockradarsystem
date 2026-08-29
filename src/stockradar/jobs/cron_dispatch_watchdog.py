"""Detect missed Cloudflare Cron -> GitHub workflow_dispatch launches.

Cloudflare Cron Triggers do not retry missed ticks. Independent GitHub
schedule checks the expected window after a grace period and fail-fasts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")

Outcome = Literal["ok", "skip_closed", "skip_not_first", "too_early", "miss"]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    workflow_file: str
    expected_hour_utc: int
    expected_minute_utc: int
    grace_minutes: int
    requires_trading_day: bool


@dataclass(frozen=True)
class WorkflowRun:
    created_at: datetime
    event: str
    status: str
    html_url: str = ""


@dataclass(frozen=True)
class WatchdogVerdict:
    outcome: Outcome
    reason: str
    target: str
    workflow_file: str
    covering_run_url: str | None = None

    @property
    def miss(self) -> bool:
        return self.outcome == "miss"


TARGETS: dict[str, TargetSpec] = {
    "patch": TargetSpec(
        name="patch",
        workflow_file="daily_universe_patch.yml",
        expected_hour_utc=3,
        expected_minute_utc=0,
        grace_minutes=35,
        requires_trading_day=True,
    ),
    "daily": TargetSpec(
        name="daily",
        workflow_file="daily.yml",
        expected_hour_utc=6,
        expected_minute_utc=45,
        grace_minutes=35,
        requires_trading_day=True,
    ),
    "monthly": TargetSpec(
        name="monthly",
        workflow_file="monthly.yml",
        expected_hour_utc=2,
        expected_minute_utc=0,
        grace_minutes=15,
        requires_trading_day=False,
    ),
}

# ADR-005 §1.3.8: independent of the three Cloudflare-miss detectors above.
MNC_POLLER_TARGET = "mnc_poller"
MNC_POLLER_WORKFLOW_FILE = "monthly_new_core_backfill_dispatch.yml"
MNC_POLLER_LOOKBACK = timedelta(minutes=45)

# Independent GitHub schedule crons (UTC). Must match cron_dispatch_watchdog.yml.
WATCHDOG_CRON_TO_TARGET: dict[str, str] = {
    "35 3 * * *": "patch",
    "20 7 * * *": "daily",
    "15 2 1 * *": "monthly",
    "5 * * * *": MNC_POLLER_TARGET,
}


def map_schedule_cron(cron: str) -> str:
    key = (cron or "").strip()
    target = WATCHDOG_CRON_TO_TARGET.get(key)
    if target is None:
        raise ValueError(f"unknown_watchdog_cron:{key}")
    return target


def parse_github_datetime(raw: str) -> datetime:
    text = (raw or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def tokyo_day_utc_window(tokyo_date: date) -> tuple[datetime, datetime]:
    start_tokyo = datetime.combine(tokyo_date, time.min, tzinfo=TOKYO)
    end_tokyo = datetime.combine(tokyo_date + timedelta(days=1), time.min, tzinfo=TOKYO)
    return start_tokyo.astimezone(timezone.utc), end_tokyo.astimezone(timezone.utc)


def expected_fire_utc(tokyo_date: date, spec: TargetSpec) -> datetime:
    # Current Cloudflare crons (02:00 / 03:00 / 06:45 UTC) all fall on Tokyo date D.
    return datetime(
        tokyo_date.year,
        tokyo_date.month,
        tokyo_date.day,
        spec.expected_hour_utc,
        spec.expected_minute_utc,
        tzinfo=timezone.utc,
    )


def parse_runs(payload: Any) -> list[WorkflowRun]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("workflow_runs") or payload.get("runs") or []
    else:
        raise ValueError("runs payload must be a list or GitHub runs object")
    parsed: list[WorkflowRun] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        created = row.get("created_at") or row.get("createdAt")
        if not created:
            continue
        parsed.append(
            WorkflowRun(
                created_at=parse_github_datetime(str(created)),
                event=str(row.get("event") or ""),
                status=str(row.get("status") or ""),
                html_url=str(row.get("html_url") or row.get("url") or ""),
            )
        )
    return parsed


def _truthy(raw: str | bool | None) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes"}


# GitHub workflow-runs API does not expose dispatch inputs, so skip_publish /
# replay after expected fire still cover. Pre-fire runs do not.
COVERING_EVENTS = frozenset({"workflow_dispatch"})
COVERING_SKEW = timedelta(minutes=2)


def covering_runs(
    *,
    spec: TargetSpec,
    tokyo_date: date,
    runs: list[WorkflowRun],
) -> list[WorkflowRun]:
    fire_at = expected_fire_utc(tokyo_date, spec)
    window_start, window_end = tokyo_day_utc_window(tokyo_date)
    earliest = max(window_start, fire_at - COVERING_SKEW)
    return [
        run
        for run in runs
        if earliest <= run.created_at < window_end and run.event in COVERING_EVENTS
    ]


def evaluate(
    *,
    spec: TargetSpec,
    now_utc: datetime,
    tokyo_date: date,
    is_open: bool,
    runs: list[WorkflowRun],
) -> WatchdogVerdict:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    if spec.name == "monthly" and tokyo_date.day != 1:
        return WatchdogVerdict(
            outcome="skip_not_first",
            reason="tokyo_date_not_first_of_month",
            target=spec.name,
            workflow_file=spec.workflow_file,
        )

    if spec.requires_trading_day and not is_open:
        return WatchdogVerdict(
            outcome="skip_closed",
            reason="tokyo_closed_session",
            target=spec.name,
            workflow_file=spec.workflow_file,
        )

    fire_at = expected_fire_utc(tokyo_date, spec)
    ready_at = fire_at + timedelta(minutes=spec.grace_minutes)
    if now_utc < ready_at:
        return WatchdogVerdict(
            outcome="too_early",
            reason=f"before_grace_end:{ready_at.isoformat()}",
            target=spec.name,
            workflow_file=spec.workflow_file,
        )

    covering = covering_runs(spec=spec, tokyo_date=tokyo_date, runs=runs)
    if covering:
        covering.sort(key=lambda r: r.created_at)
        chosen = covering[-1]
        return WatchdogVerdict(
            outcome="ok",
            reason="dispatch_observed",
            target=spec.name,
            workflow_file=spec.workflow_file,
            covering_run_url=chosen.html_url or None,
        )
    return WatchdogVerdict(
        outcome="miss",
        reason="no_dispatch_in_covering_window",
        target=spec.name,
        workflow_file=spec.workflow_file,
    )


def evaluate_mnc_poller_liveness(
    *,
    enabled: bool,
    now_utc: datetime,
    runs: list[WorkflowRun],
    lookback: timedelta = MNC_POLLER_LOOKBACK,
) -> WatchdogVerdict:
    """ADR-005 §1.3.8: while MNC_DISPATCH_ENABLED, require poller dispatch in lookback."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    if not enabled:
        return WatchdogVerdict(
            outcome="ok",
            reason="mnc_dispatch_disabled",
            target=MNC_POLLER_TARGET,
            workflow_file=MNC_POLLER_WORKFLOW_FILE,
        )

    earliest = now_utc - lookback
    covering = [
        run
        for run in runs
        if run.event in COVERING_EVENTS and earliest <= run.created_at <= now_utc
    ]
    if covering:
        covering.sort(key=lambda r: r.created_at)
        chosen = covering[-1]
        return WatchdogVerdict(
            outcome="ok",
            reason="poller_dispatch_observed",
            target=MNC_POLLER_TARGET,
            workflow_file=MNC_POLLER_WORKFLOW_FILE,
            covering_run_url=chosen.html_url or None,
        )
    return WatchdogVerdict(
        outcome="miss",
        reason="no_poller_dispatch_in_lookback",
        target=MNC_POLLER_TARGET,
        workflow_file=MNC_POLLER_WORKFLOW_FILE,
    )


def _append_github_output(fields: dict[str, str]) -> None:
    path = os_github_output()
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in fields.items():
            fh.write(f"{key}={value}\n")


def os_github_output() -> str | None:
    path = os.environ.get("GITHUB_OUTPUT")
    return path or None


def verdict_to_outputs(verdict: WatchdogVerdict) -> dict[str, str]:
    return {
        "outcome": verdict.outcome,
        "miss": "true" if verdict.miss else "false",
        "target": verdict.target,
        "workflow_file": verdict.workflow_file,
        "reason": verdict.reason,
        "covering_run_url": verdict.covering_run_url or "",
    }


def _print_verdict(verdict: WatchdogVerdict) -> None:
    print(f"outcome={verdict.outcome}")
    print(f"miss={'true' if verdict.miss else 'false'}")
    print(f"target={verdict.target}")
    print(f"workflow_file={verdict.workflow_file}")
    print(f"reason={verdict.reason}")
    if verdict.covering_run_url:
        print(f"covering_run_url={verdict.covering_run_url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cloudflare cron dispatch watchdog")
    parser.add_argument("--map-schedule", default="", help="Print target name for watchdog cron")
    parser.add_argument(
        "--target",
        default="",
        help="daily|patch|monthly|mnc_poller",
    )
    parser.add_argument("--runs-json", default="", help="Path to GitHub workflow runs JSON")
    parser.add_argument("--tokyo-date", default="", help="YYYY-MM-DD Asia/Tokyo")
    parser.add_argument("--is-open", default="", help="True/False from resolve_trading_day")
    parser.add_argument("--now-utc", default="", help="ISO-8601 UTC override")
    parser.add_argument(
        "--mnc-dispatch-enabled",
        default="",
        help="True/False; required for target=mnc_poller (default false when empty)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Always exit 0 after writing outputs (GitHub Actions evaluator step)",
    )
    args = parser.parse_args(argv)

    if args.map_schedule:
        try:
            print(map_schedule_cron(args.map_schedule))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    target_name = (args.target or "").strip()
    if args.now_utc.strip():
        now_utc = parse_github_datetime(args.now_utc.strip())
    else:
        now_utc = datetime.now(timezone.utc)

    if not args.runs_json:
        print("error: --runs-json is required", file=sys.stderr)
        return 1
    try:
        payload = json.loads(Path(args.runs_json).read_text(encoding="utf-8"))
        runs = parse_runs(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: cannot read runs json: {exc}", file=sys.stderr)
        return 1

    if target_name == MNC_POLLER_TARGET:
        enabled = _truthy(args.mnc_dispatch_enabled)
        verdict = evaluate_mnc_poller_liveness(
            enabled=enabled,
            now_utc=now_utc,
            runs=runs,
        )
        _print_verdict(verdict)
        _append_github_output(verdict_to_outputs(verdict))
        if verdict.miss and not args.report_only:
            return 2
        return 0

    spec = TARGETS.get(target_name)
    if spec is None:
        print(f"error: unknown target {target_name!r}", file=sys.stderr)
        return 1
    if not args.tokyo_date:
        print("error: --tokyo-date is required", file=sys.stderr)
        return 1

    try:
        tokyo_date = date.fromisoformat(args.tokyo_date.strip())
    except ValueError:
        print(f"error: invalid --tokyo-date {args.tokyo_date!r}", file=sys.stderr)
        return 1

    verdict = evaluate(
        spec=spec,
        now_utc=now_utc,
        tokyo_date=tokyo_date,
        is_open=_truthy(args.is_open),
        runs=runs,
    )
    _print_verdict(verdict)
    _append_github_output(verdict_to_outputs(verdict))
    if verdict.miss and not args.report_only:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
