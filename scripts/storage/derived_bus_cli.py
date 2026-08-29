"""Derived writer bus CLI: put-generation and verify-digest (Phase 4.5)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stockradar.storage.daily_seed_lease import wait_and_collect_seed_lease_skips
from stockradar.jobs.write_derived_generation import (  # noqa: E402
    DerivedGenerationRequest,
    SnapshotInput,
    run_derived_generation,
)
from stockradar.metrics.registry_spec import load_metric_set_spec  # noqa: E402
from stockradar.storage.derived_adapters import (  # noqa: E402
    generation_store_from_env,
    is_derived_generation_fake,
    registry_store_from_env,
    r2_store_from_env,
)
from stockradar.storage.derived_generation import MetricGenerationPort  # noqa: E402
from stockradar.storage.derived_snapshot import (  # noqa: E402
    build_snapshot_rows,
    compute_snapshot_logical_digest,
)
from stockradar.storage.mapping_catalog import load_mapping  # noqa: E402
from stockradar.storage.metric_registry import FakeMetricRegistryStore, MetricRegistryPort  # noqa: E402
from stockradar.storage.phase4_5_rollout import (  # noqa: E402
    PreflightResult,
    ResolveResult,
    ResolvedMetricSet,
    SetResolutionContext,
    preflight_derived_write,
    resolve_metric_set_version_id,
    resolve_phase4_5_rollout_stage,
    validate_resolved_set_for_mode,
)
from stockradar.storage.r2_object_store import R2ObjectStorePort  # noqa: E402


def _emit(payload: dict[str, object], json_output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if json_output:
        Path(json_output).parent.mkdir(parents=True, exist_ok=True)
        with open(json_output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


def _stage(args: argparse.Namespace) -> str:
    return resolve_phase4_5_rollout_stage(
        cli_override=getattr(args, "phase4_5_rollout_stage", None),
        mapping=load_mapping(),
    )


def _registry_store(args: argparse.Namespace) -> MetricRegistryPort:
    store = registry_store_from_env()
    if is_derived_generation_fake() and args.metric_set_version_id:
        fake_store = store
        if not isinstance(fake_store, FakeMetricRegistryStore):
            fake_store = FakeMetricRegistryStore()
            store = fake_store
        set_id = fake_store.seed_set(
            set_id=args.metric_set_version_id,
            lifecycle=args.lifecycle_status,
        )
        if args.lifecycle_status == "active":
            fake_store.active_metric_set = {
                "pointer_key": "default",
                "metric_set_version_id": set_id,
                "writer_workflow": args.workflow if hasattr(args, "workflow") else "derived_writer.yml",
                "source_github_run_id": int(getattr(args, "github_run_id", 1)),
            }
    return store


def _generation_store() -> MetricGenerationPort:
    return generation_store_from_env()


def _r2_store() -> R2ObjectStorePort:
    return r2_store_from_env()


def _load_snapshot_values(path: Path) -> dict[str, dict[str, object]]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("snapshot JSON must be an object keyed by instrument_code")
    return data


def _phase_abc_preflight(
    *,
    stage: str,
    mode: str,
    metric_set_version_id: str | None,
    registry: MetricRegistryPort,
) -> tuple[int, str | None, str | None]:
    """Phase A→B→C gate. Returns (exit_code, resolved_set_id, reason)."""
    preflight = preflight_derived_write(stage, mode)
    if preflight == PreflightResult.SKIP0:
        return 0, None, "preflight_skip0"
    if preflight == PreflightResult.EXIT2:
        return 2, None, "preflight_exit2"

    active_id = registry.get_active_metric_set_id()
    resolve_result, resolved_id = resolve_metric_set_version_id(
        stage=stage,
        mode=mode,
        metric_set_version_id=metric_set_version_id,
        ctx=SetResolutionContext(active_metric_set_id=active_id),
    )
    if resolve_result == ResolveResult.SKIP0:
        return 0, None, "resolve_skip0"
    if resolve_result == ResolveResult.NO_RESOLVE_REPLAY:
        return 0, None, "replay_no_write"
    if resolve_result in {
        ResolveResult.EXIT2,
        ResolveResult.FLAG_REQUIRED,
        ResolveResult.FLAG_MUST_MATCH_ACTIVE,
    }:
        return 2, None, f"resolve_{resolve_result.value}"
    if not resolved_id:
        return 2, None, "resolve_missing_uuid"

    row = registry.get_metric_set_version(resolved_id)
    if row is None:
        return 2, None, "unknown_metric_set_version"
    resolved = ResolvedMetricSet(
        metric_set_version_id=resolved_id,
        lifecycle_status=str(row.get("lifecycle_status") or "draft"),
        is_active=active_id == resolved_id,
    )
    if not validate_resolved_set_for_mode(
        stage=stage,
        mode=mode,
        resolved=resolved,
        ctx=SetResolutionContext(active_metric_set_id=active_id),
    ):
        return 2, None, "resolved_set_invalid"
    return 0, resolved_id, None


def cmd_put_generation(args: argparse.Namespace) -> int:
    stage = _stage(args)
    registry = _registry_store(args)
    exit_code, resolved_id, reason = _phase_abc_preflight(
        stage=stage,
        mode=args.mode,
        metric_set_version_id=args.metric_set_version_id,
        registry=registry,
    )
    if exit_code != 0 or resolved_id is None:
        _emit(
            {
                "status": "skipped" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "reason": reason,
            },
            args.json_output,
        )
        return exit_code

    metric_spec = load_metric_set_spec(args.metric_set_yaml)
    metric_types = {member.metric_key: member.value_type for member in metric_spec.members}
    values_by_instrument = _load_snapshot_values(Path(args.snapshot_json))
    snapshot_input = SnapshotInput(
        metric_keys_ordered=metric_spec.metric_keys_ordered,
        metric_types=metric_types,
        values_by_instrument=values_by_instrument,
        layer1_input_fingerprint=args.layer1_input_fingerprint,
    )
    row = registry.get_metric_set_version(resolved_id)
    if row is None:
        _emit(
            {"status": "error", "exit_code": 2, "reason": "unknown_metric_set_version"},
            args.json_output,
        )
        return 2

    expected_old_digest = args.expected_old_digest
    if args.mode == "reconcile":
        if not expected_old_digest:
            expected_old_digest = _generation_store().get_committed_snapshot_digest(
                metric_set_version_id=resolved_id,
                trade_date=args.trade_date,
            )
        if not expected_old_digest and not is_derived_generation_fake():
            _emit(
                {
                    "status": "error",
                    "exit_code": 2,
                    "reason": "expected_old_digest_required_for_reconcile",
                },
                args.json_output,
            )
            return 2

    request = DerivedGenerationRequest(
        stage=stage,
        mode=args.mode,
        trade_date=args.trade_date,
        repository=args.repository,
        workflow=args.workflow,
        github_run_id=int(args.github_run_id),
        metric_set_version_id=resolved_id,
        active_metric_set_id=registry.get_active_metric_set_id(),
        lifecycle_status=str(row.get("lifecycle_status") or "shadow"),
        is_active=registry.get_active_metric_set_id() == resolved_id,
        is_current_latest_trade_date=args.is_current_latest_trade_date.lower()
        in ("true", "1", "yes"),
        expected_old_digest=expected_old_digest,
        writer_workflow=args.workflow,
        set_fingerprint=metric_spec.set_fingerprint,
    )
    latest_rows: list[dict[str, object]] | None = None
    if request.is_current_latest_trade_date:
        snapshot_rows = build_snapshot_rows(
            trade_date=args.trade_date,
            metric_set_version_id=resolved_id,
            metric_keys_ordered=metric_spec.metric_keys_ordered,
            metric_types=metric_types,
            values_by_instrument=values_by_instrument,
        )
        logical_digest, _ = compute_snapshot_logical_digest(
            trade_date=args.trade_date,
            metric_set_version_id=resolved_id,
            rows=snapshot_rows,
        )
        latest_rows = [
            {
                "instrument_code": instrument_code,
                "trade_date": args.trade_date,
                "values_json": values_by_instrument[instrument_code],
                "logical_digest": logical_digest,
            }
            for instrument_code in sorted(values_by_instrument)
        ]
    lease_codes: list[str] = []
    lease_waited = 0.0
    try:
        from datetime import datetime, timezone

        from stockradar.storage.supabase_client import SupabaseRestAdapter, control_adapter_from_env

        adapter = control_adapter_from_env()
        membership = list(snapshot_input.values_by_instrument.keys())

        def _fetch_rows():
            if adapter is None or not hasattr(adapter, "_request"):
                return []
            if not isinstance(adapter, SupabaseRestAdapter):
                return []
            # Avoid huge in.(membership) URLs (414). Fetch active seed/repair leases and
            # filter to membership in list_active_seed_lease_codes_from_rows.
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            resp = adapter._request(
                "GET",
                "/rest/v1/series_write_leases",
                params={
                    "owner_kind": "in.(series_seed,series_repair)",
                    "expires_at": f"gt.{now_iso}",
                    "select": "instrument_code,owner_kind,expires_at",
                },
            )
            if resp.status_code == 404:
                # Table not applied yet: Daily must still run.
                return []
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"series_write_leases query failed: HTTP {resp.status_code}"
                )
            data = resp.json()
            return data if isinstance(data, list) else []

        decision = wait_and_collect_seed_lease_skips(
            membership_codes=membership,
            fetch_active_rows=_fetch_rows,
            max_wait_seconds=120.0,
            poll_seconds=5.0,
        )
        lease_codes = list(decision.skipped_codes)
        lease_waited = float(decision.waited_seconds)
    except Exception as exc:
        print(f"error: seed lease poll failed: {exc}", file=sys.stderr)
        return 2

    result = run_derived_generation(
        request,
        snapshot_input=snapshot_input,
        generation_store=_generation_store(),
        r2_store=_r2_store(),
        latest_rows=latest_rows,
        series_builders=None,
        active_seed_lease_codes=lease_codes or None,
        seed_lease_waited_seconds=lease_waited,
    )
    _emit(
        {
            "status": result.status,
            "exit_code": result.exit_code,
            "generation_id": result.generation_id,
            "logical_digest": result.logical_digest,
            "object_keys": list(result.object_keys),
            "reason": result.reason,
            "series_count": result.series_count,
            "flags": list(getattr(result, "flags", ()) or ()),
            "lease_skipped_codes": list(getattr(result, "lease_skipped_codes", ()) or ()),
            "r2_concurrency": result.r2_concurrency,
            "elapsed_ms": {
                "prefetch": result.prefetch_elapsed_ms,
                "put": result.put_elapsed_ms,
                "rpc": result.rpc_elapsed_ms,
            },
        },
        args.json_output,
    )
    return result.exit_code


def cmd_verify_digest(args: argparse.Namespace) -> int:
    stage = _stage(args)
    registry = _registry_store(args)
    exit_code, resolved_id, reason = _phase_abc_preflight(
        stage=stage,
        mode=args.mode,
        metric_set_version_id=args.metric_set_version_id,
        registry=registry,
    )
    if exit_code != 0 or resolved_id is None:
        _emit(
            {
                "status": "skipped" if exit_code == 0 else "error",
                "verified": False,
                "reason": reason,
            },
            args.json_output,
        )
        return exit_code

    metric_spec = load_metric_set_spec(args.metric_set_yaml)
    metric_types = {member.metric_key: member.value_type for member in metric_spec.members}
    values_by_instrument = _load_snapshot_values(Path(args.snapshot_json))
    rows = build_snapshot_rows(
        trade_date=args.trade_date,
        metric_set_version_id=resolved_id,
        metric_keys_ordered=metric_spec.metric_keys_ordered,
        metric_types=metric_types,
        values_by_instrument=values_by_instrument,
    )
    digest, canonical_bytes = compute_snapshot_logical_digest(
        trade_date=args.trade_date,
        metric_set_version_id=resolved_id,
        rows=rows,
    )
    expected = (args.expected_digest or "").strip().lower()
    if not expected:
        _emit(
            {
                "status": "error",
                "verified": False,
                "reason": "expected_digest_required",
                "logical_digest": digest,
            },
            args.json_output,
        )
        return 2
    verified = digest == expected
    _emit(
        {
            "status": "ok" if verified else "error",
            "verified": verified,
            "logical_digest": digest,
            "canonical_byte_length": len(canonical_bytes),
            "expected_digest": expected or None,
        },
        args.json_output,
    )
    return 0 if verified else 2


def cmd_get_object(args: argparse.Namespace) -> int:
    store = _r2_store()
    dest = Path(args.local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(store.get_object(args.object_key))
    _emit({"status": "ok", "object_key": args.object_key, "local_path": str(dest)}, None)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Derived writer bus CLI (Fake-friendly).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--phase4-5-rollout-stage")
    common.add_argument("--mode", default="normal")
    common.add_argument("--trade-date", required=True)
    common.add_argument("--metric-set-version-id")
    common.add_argument("--lifecycle-status", default="shadow")
    common.add_argument("--metric-set-yaml")
    common.add_argument("--snapshot-json", required=True)
    common.add_argument("--json-output")

    put = sub.add_parser("put-generation", parents=[common])
    put.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "local/test"))
    put.add_argument("--workflow", default="derived_writer.yml")
    put.add_argument("--github-run-id", default=os.environ.get("GITHUB_RUN_ID", "1"))
    put.add_argument("--layer1-input-fingerprint", required=True)
    put.add_argument("--expected-old-digest")
    put.add_argument("--is-current-latest-trade-date", default="false")
    put.set_defaults(func=cmd_put_generation)

    verify = sub.add_parser("verify-digest", parents=[common])
    verify.add_argument("--expected-digest")
    verify.set_defaults(func=cmd_verify_digest)

    geto = sub.add_parser("get-object")
    geto.add_argument("--object-key", required=True)
    geto.add_argument("--local-path", required=True)
    geto.set_defaults(func=cmd_get_object)

    args = parser.parse_args(argv)
    if getattr(args, "metric_set_yaml", None) is None and hasattr(args, "snapshot_json"):
        args.metric_set_yaml = str(
            _REPO_ROOT / "config" / "metrics" / "metric_set_v1.yaml"
        )
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
