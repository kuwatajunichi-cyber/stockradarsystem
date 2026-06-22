"""Aggregate Phase 2b artifact handoff JSON files and enforce gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_payloads(handoff_dir: Path) -> dict[str, dict[str, object]]:
    by_entry: dict[str, dict[str, object]] = {}
    for path in sorted(handoff_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry_id = str(payload.get("entry_id") or path.stem)
        by_entry[entry_id] = payload
    return by_entry


def _handoff_ok(payload: dict[str, object], *, optional: bool) -> bool:
    status = payload.get("status")
    if status == "ok":
        return payload.get("handoff_source") in {"r2", "github_fallback"}
    return optional and status == "skipped_optional_missing"


def _producer_status(payload: dict[str, object] | None, *, optional: bool) -> str:
    if payload is None:
        return "optional_skipped" if optional else "failed"
    status = payload.get("status")
    if status == "skipped_optional_missing":
        return "optional_skipped"
    if payload.get("r2_put_ok") is True:
        return "ok"
    if payload.get("github_upload_ok") is True:
        return "degraded"
    return "optional_skipped" if optional else "failed"


def _apply_github_upload_ok(
    by_entry: dict[str, dict[str, object]],
    *,
    github_upload_ok: frozenset[str],
) -> None:
    for entry_id, payload in by_entry.items():
        payload["github_upload_ok"] = entry_id in github_upload_ok


def _producer_handoff_ok(status: str) -> bool:
    return status in {"ok", "degraded", "optional_skipped"}


def write_producer_summary(
    *,
    handoff_dir: Path,
    title: str,
    required: list[str],
    optional: list[str],
    github_upload_ok: frozenset[str] | None = None,
) -> tuple[list[str], int]:
    by_entry = _load_payloads(handoff_dir)
    upload_ok = github_upload_ok if github_upload_ok is not None else frozenset(required)
    _apply_github_upload_ok(by_entry, github_upload_ok=upload_ok)

    lines = [f"## {title}"]
    degraded: list[str] = []
    skipped_optional: list[str] = []
    failed_required: list[str] = []

    for entry_id in required + optional:
        is_optional = entry_id in optional
        payload = by_entry.get(entry_id)
        handoff_status = _producer_status(payload, optional=is_optional)
        payload = payload or {}

        r2_put_ok = payload.get("r2_put_ok")
        gh_ok = payload.get("github_upload_ok")
        degraded_reason = payload.get("degraded_reason") or payload.get("reason") or ""
        manifest_key = payload.get("manifest_logical_key", "")

        if handoff_status == "ok":
            mk_part = f" manifest_key=`{manifest_key}`" if manifest_key else ""
            lines.append(
                f"- {entry_id}: producer_handoff_status=`ok` r2_put_ok=`true` "
                f"github_upload_ok=`{gh_ok}`{mk_part}"
            )
        elif handoff_status == "degraded":
            degraded.append(entry_id)
            lines.append(
                f"- {entry_id}: producer_handoff_status=`degraded` r2_put_ok=`false` "
                f"github_upload_ok=`{gh_ok}` degraded_reason=`{degraded_reason}`"
            )
        elif handoff_status == "optional_skipped":
            skipped_optional.append(entry_id)
            lines.append(
                f"- {entry_id}: producer_handoff_status=`optional_skipped` ({degraded_reason})"
            )
        else:
            failed_required.append(entry_id)
            lines.append(
                f"- {entry_id}: producer_handoff_status=`failed` r2_put_ok=`{r2_put_ok}` "
                f"github_upload_ok=`{gh_ok}` ({degraded_reason})"
            )

    ok_count = sum(
        1
        for entry_id in required
        if _producer_handoff_ok(_producer_status(by_entry.get(entry_id), optional=False))
    )
    lines.append(f"- required_producer_handoff_ok_count: `{ok_count}`")
    if degraded:
        lines.append("- producer_degraded: `" + ", ".join(degraded) + "`")
    if skipped_optional:
        lines.append("- optional_skipped: `" + ", ".join(skipped_optional) + "`")
    if failed_required:
        lines.append("- producer_handoff_failed_required: `" + ", ".join(failed_required) + "`")
    return lines, 1 if failed_required else 0


def write_summary(
    *,
    handoff_dir: Path,
    title: str,
    required: list[str],
    optional: list[str],
) -> tuple[list[str], int]:
    by_entry = _load_payloads(handoff_dir)
    lines = [f"## {title}"]
    fallback_used: list[str] = []
    skipped_optional: list[str] = []
    failed_required: list[str] = []

    for entry_id in required + optional:
        payload = by_entry.get(entry_id)
        if payload is None:
            if entry_id in required:
                failed_required.append(entry_id)
                lines.append(f"- {entry_id}: `missing_handoff_record`")
            else:
                skipped_optional.append(entry_id)
                lines.append(f"- {entry_id}: `optional_missing`")
            continue

        status = payload.get("status")
        source = payload.get("handoff_source")
        if status == "skipped_optional_missing" and entry_id in optional:
            skipped_optional.append(entry_id)
            reason = payload.get("degraded_reason") or payload.get("reason") or ""
            lines.append(f"- {entry_id}: skipped_optional ({reason})")
        elif _handoff_ok(payload, optional=entry_id in optional):
            sha = payload.get("sha256", "")
            lines.append(f"- {entry_id}: ok handoff_source=`{source}` sha256=`{sha}`")
            if payload.get("fallback_used"):
                fallback_used.append(entry_id)
        elif entry_id in required:
            failed_required.append(entry_id)
            reason = payload.get("degraded_reason") or payload.get("reason") or ""
            lines.append(f"- {entry_id}: `{status}` ({reason})")
        else:
            skipped_optional.append(entry_id)
            lines.append(f"- {entry_id}: optional `{status}`")

    ok_count = sum(
        1
        for entry_id in required
        if entry_id in by_entry and _handoff_ok(by_entry[entry_id], optional=False)
    )
    lines.append(f"- required_handoff_ok_count: `{ok_count}`")
    if fallback_used:
        lines.append("- fallback_used: `" + ", ".join(fallback_used) + "`")
    if skipped_optional:
        lines.append("- optional_skipped: `" + ", ".join(skipped_optional) + "`")
    if failed_required:
        lines.append("- handoff_failed_required: `" + ", ".join(failed_required) + "`")
    return lines, 1 if failed_required else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Phase 2b handoff summary")
    parser.add_argument("--handoff-dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--required", nargs="*", default=[])
    parser.add_argument("--optional", nargs="*", default=[])
    parser.add_argument(
        "--mode",
        choices=("consumer", "producer"),
        default="consumer",
        help="consumer=get/fallback gate; producer=R2 put + GitHub upload gate",
    )
    parser.add_argument(
        "--github-upload-ok",
        nargs="*",
        default=[],
        help="entry IDs with successful GitHub artifact upload (producer mode)",
    )
    args = parser.parse_args(argv)
    handoff_dir = Path(args.handoff_dir)
    required = list(args.required)
    optional = list(args.optional)
    if args.mode == "producer":
        lines, exit_code = write_producer_summary(
            handoff_dir=handoff_dir,
            title=args.title,
            required=required,
            optional=optional,
            github_upload_ok=frozenset(args.github_upload_ok) if args.github_upload_ok else None,
        )
    else:
        lines, exit_code = write_summary(
            handoff_dir=handoff_dir,
            title=args.title,
            required=required,
            optional=optional,
        )
    print("\n".join(lines))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
