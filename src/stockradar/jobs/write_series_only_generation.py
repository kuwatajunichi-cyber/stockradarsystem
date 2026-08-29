"""Dedicated series_only writer for ADR-005 series_seed / series_repair.

Does NOT call write_derived_generation / run_derived_generation (those require snapshot).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.metrics.registry_spec import (  # noqa: E402
    load_metric_set_spec,
    metric_set_is_series_seedable,
    require_seed_metric_input_contract,
)
from stockradar.storage.derived_generation import (  # noqa: E402
    ArtifactProfile,
    BeginGenerationRequest,
    SeriesCoordinateCAS,
    SourceRunIdentity,
    expected_derived_object_count,
    resolve_artifact_profile,
)
from stockradar.storage.derived_series import merge_missing_dates_only  # noqa: E402
from stockradar.storage.phase4_5_rollout import (  # noqa: E402
    normalize_run_mode,
    write_allowed,
)
from stockradar.storage.series_seed import (  # noqa: E402
    classify_seed_trade_date_codes,
    series_only_expected_object_count,
    validate_series_repair_approver,
)
from stockradar.utils.yf_cache_long_history import fetch_long_history_bounded  # noqa: E402


@dataclass(frozen=True)
class SeriesOnlyWritePlan:
    request_id: str
    mode: str
    trade_date: str
    write_codes: tuple[str, ...]
    resolved_noop_codes: tuple[str, ...]
    expected_object_count: int
    artifact_profile: str


def plan_series_only_trade_date(
    *,
    request_id: str,
    mode: str,
    trade_date: str,
    candidate_codes: Sequence[str],
    existing_dates_by_code: Mapping[str, Sequence[str]],
    stage: str = "4.5c",
) -> SeriesOnlyWritePlan:
    normalized = normalize_run_mode(mode)
    if normalized not in {"series_seed", "series_repair"}:
        raise ValueError(f"series_only writer rejects mode {mode!r}")
    profile = resolve_artifact_profile(stage=stage, mode=normalized)
    if profile != ArtifactProfile.SERIES_ONLY:
        raise ValueError(f"expected SERIES_ONLY profile, got {profile}")
    if not write_allowed(
        stage=stage,
        mode=normalized,
        set_is_active=True,
        set_lifecycle="active",
        artifact="series",
    ):
        raise RuntimeError("series write not allowed for stage/mode")
    split = classify_seed_trade_date_codes(
        candidate_codes=candidate_codes,
        existing_dates_by_code=existing_dates_by_code,
        trade_date=trade_date,
    )
    write_codes = tuple(split["write"])
    noop = tuple(split["resolved_noop"])
    expected = series_only_expected_object_count(len(write_codes))
    # Keep in sync with derived_generation.expected_derived_object_count
    if write_codes:
        assert expected == expected_derived_object_count(
            profile=ArtifactProfile.SERIES_ONLY, instrument_count=len(write_codes)
        )
    return SeriesOnlyWritePlan(
        request_id=request_id,
        mode=normalized,
        trade_date=trade_date,
        write_codes=write_codes,
        resolved_noop_codes=noop,
        expected_object_count=expected,
        artifact_profile=profile.value,
    )


def ensure_seed_catalog_or_block() -> None:
    spec = load_metric_set_spec()
    require_seed_metric_input_contract(spec)
    if not metric_set_is_series_seedable(spec):
        raise RuntimeError("blocked:metric_not_series_seedable")


def build_begin_request_for_plan(
    *,
    plan: SeriesOnlyWritePlan,
    metric_set_version_id: str,
    github_run_id: int,
    repository: str = "local/stockradarsystem",
    prior_absent_by_code: Mapping[str, bool] | None = None,
    expected_prior_digest_by_code: Mapping[str, str] | None = None,
) -> BeginGenerationRequest:
    if plan.expected_object_count == 0:
        raise ValueError("no generation when expected_object_count is 0")
    coords: list[SeriesCoordinateCAS] = []
    prior_absent = prior_absent_by_code or {}
    digests = expected_prior_digest_by_code or {}
    year = int(str(plan.trade_date)[:4])
    for code in plan.write_codes:
        coords.append(
            SeriesCoordinateCAS(
                instrument_code=code,
                series_year=year,
                expected_prior_logical_digest=digests.get(code),
                prior_absent=bool(prior_absent.get(code, code not in digests)),
            )
        )
    return BeginGenerationRequest(
        source=SourceRunIdentity(
            repository=repository,
            workflow="monthly_new_core_backfill.yml",
            github_run_id=github_run_id,
            metric_set_version_id=metric_set_version_id,
            trade_date=plan.trade_date,
            mode=plan.mode,  # type: ignore[arg-type]
        ),
        artifact_profile=ArtifactProfile.SERIES_ONLY,
        expected_object_count=plan.expected_object_count,
        series_coordinates=tuple(coords),
        request_id=plan.request_id,
    )


def merge_seed_observation(
    *,
    trade_date: str,
    metric_keys_ordered: list[str],
    values: dict[str, Any],
    instrument_code: str,
    prior_dates: list[str] | None,
    prior_series: dict[str, list[Any]] | None,
    prior_flags: list[dict[str, Any]] | None,
) -> tuple[list[str], dict[str, list[Any]], list[dict[str, Any]], bool]:
    return merge_missing_dates_only(
        trade_date=trade_date,
        metric_keys_ordered=metric_keys_ordered,
        values=values,
        instrument_code=instrument_code,
        prior_dates=prior_dates,
        prior_series=prior_series,
        prior_flags=prior_flags,
    )


def fetch_bounded_layer1(
    *,
    required_input_start: datetime,
    coverage_end: datetime,
    fetch_chunk,
):
    return fetch_long_history_bounded(
        required_input_start=required_input_start,
        coverage_end=coverage_end,
        fetch_chunk=fetch_chunk,
    )


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        ensure_seed_catalog_or_block()
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    existing = json.loads(args.existing_dates_json)
    plan = plan_series_only_trade_date(
        request_id=args.request_id,
        mode=args.mode,
        trade_date=args.trade_date,
        candidate_codes=json.loads(args.codes_json),
        existing_dates_by_code=existing,
    )
    if args.mode == "series_repair":
        validate_series_repair_approver(
            approver_github_login=args.approver_github_login or "",
            worker_github_actor=args.worker_github_actor
            or os.environ.get("GITHUB_ACTOR", ""),
        )
    payload = {
        "status": "ok",
        "request_id": plan.request_id,
        "mode": plan.mode,
        "trade_date": plan.trade_date,
        "write_codes": list(plan.write_codes),
        "resolved_noop_codes": list(plan.resolved_noop_codes),
        "expected_object_count": plan.expected_object_count,
        "artifact_profile": plan.artifact_profile,
        "generation_required": plan.expected_object_count > 0,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-005 series_only writer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan-trade-date")
    p.add_argument("--request-id", required=True)
    p.add_argument("--mode", default="series_seed", choices=["series_seed", "series_repair"])
    p.add_argument("--trade-date", required=True)
    p.add_argument("--codes-json", required=True)
    p.add_argument("--existing-dates-json", default="{}")
    p.add_argument("--approver-github-login", default="")
    p.add_argument("--worker-github-actor", default="")
    p.set_defaults(func=cmd_plan)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
