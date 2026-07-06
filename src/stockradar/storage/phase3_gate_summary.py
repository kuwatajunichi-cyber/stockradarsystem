"""Phase 3 live gate fields for GitHub Actions Step Summary."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _load_json(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def cache_get_gate_lines(
    get_json: Path | None,
    *,
    fallback_cache_source: str | None = None,
) -> list[str]:
    payload = _load_json(get_json)
    if payload is None:
        if fallback_cache_source:
            return [
                "- warm_cache_get_status: `miss`",
                f"- cache_source: `{fallback_cache_source}`",
            ]
        return ["- warm_cache_get_status: `(no json)`"]

    status = str(payload.get("status") or "unknown")
    lines = [f"- warm_cache_get_status: `{status}`"]
    cache_source = payload.get("cache_source")
    if cache_source is None and status == "miss":
        cache_source = fallback_cache_source or "miss"
    if cache_source is not None:
        lines.append(f"- cache_source: `{cache_source}`")
    reason = payload.get("reason")
    if reason:
        lines.append(f"- warm_cache_get_reason: `{reason}`")
    return lines


def cache_put_gate_lines(put_json: Path | None) -> list[str]:
    payload = _load_json(put_json)
    if payload is None:
        return ["- warm_cache_put_status: `(no json)`"]

    status = str(payload.get("status") or "unknown")
    lines = [f"- warm_cache_put_status: `{status}`"]
    cache_source = payload.get("cache_source")
    if cache_source is not None:
        lines.append(f"- cache_source: `{cache_source}`")
    supabase_ok = payload.get("supabase_commit_ok")
    if supabase_ok is not None:
        lines.append(f"- supabase_commit_ok: `{supabase_ok}`")
    supabase_failed = payload.get("supabase_commit_failed")
    if supabase_failed:
        lines.append(f"- supabase_commit_failed: `{supabase_failed}`")
    return lines


def write_cache_section(
    *,
    title: str,
    warm_cache_key: str,
    get_json: Path | None = None,
    put_json: Path | None = None,
    fallback_cache_source: str | None = None,
    extra_lines: list[str] | None = None,
    summary_path: Path | None = None,
) -> None:
    lines = [f"## {title}", f"- warm_cache_key: `{warm_cache_key}`"]
    lines.extend(cache_get_gate_lines(get_json, fallback_cache_source=fallback_cache_source))
    lines.extend(cache_put_gate_lines(put_json))
    if extra_lines:
        lines.extend(extra_lines)
    text = "\n".join(lines) + "\n"
    out = summary_path or Path(os.environ["GITHUB_STEP_SUMMARY"])
    with out.open("a", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append Phase 3 cache gate lines to Step Summary")
    parser.add_argument("--title", required=True)
    parser.add_argument("--warm-cache-key", required=True)
    parser.add_argument("--get-json", default=None)
    parser.add_argument("--put-json", default=None)
    parser.add_argument("--fallback-cache-source", default=None)
    parser.add_argument("--extra-line", action="append", default=[])
    args = parser.parse_args(argv)

    write_cache_section(
        title=args.title,
        warm_cache_key=args.warm_cache_key,
        get_json=Path(args.get_json) if args.get_json else None,
        put_json=Path(args.put_json) if args.put_json else None,
        fallback_cache_source=args.fallback_cache_source,
        extra_lines=list(args.extra_line),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
