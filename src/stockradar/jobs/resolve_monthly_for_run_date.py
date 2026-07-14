"""
Resolve monthly-* tag for run_date (GitHub releases and/or Supabase snapshots).

Usage:
  python -m stockradar.jobs.resolve_monthly_for_run_date \\
    --run-date YYYY-MM-DD --source auto --tags-file /tmp/monthly_tags.txt
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from stockradar.storage.mapping_catalog import load_mapping
from stockradar.storage.phase4_rollout import (
    monthly_read_allows_github_fallback,
    monthly_read_uses_supabase_primary,
    resolve_phase4_rollout_stage,
)
from stockradar.storage.supabase_client import FakeSupabaseControlAdapter, SupabaseRestAdapter
from stockradar.universe.monthly_release_pick import MonthlyReleasePick, pick_monthly_release
from stockradar.universe.monthly_snapshot_list import list_committed_monthly_tags


def _append_github_output(path: str | None, key: str, value: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def _escape_kv(s: str) -> str:
    return s.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def _monthly_tag_sort_key(tag: str) -> tuple[str, int]:
    parts = tag.split("-")
    if len(parts) >= 3 and len(parts[1]) == 8 and parts[1].isdigit():
        try:
            return parts[1], int(parts[2])
        except ValueError:
            pass
    return "", 0


def _read_tags_file(tags_file: Path) -> list[str]:
    if not tags_file.is_file():
        raise ValueError(f"tags file not found: {tags_file}")
    return [ln.strip() for ln in tags_file.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _supabase_tags() -> list[str]:
    if os.environ.get("SUPABASE_CONTROL_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return list_committed_monthly_tags(FakeSupabaseControlAdapter())
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        return []
    return list_committed_monthly_tags(SupabaseRestAdapter.from_env())


def resolve_monthly_tag(
    run_date: date,
    *,
    source: str,
    tags_file: Path | None,
    phase4_stage: str,
    sb_tags: list[str] | None = None,
) -> tuple[MonthlyReleasePick, str]:
    """Return (pick, monthly_resolve_source)."""
    src = source.strip().lower()
    stage = phase4_stage

    if src == "github":
        if tags_file is None:
            raise ValueError("--tags-file required for source=github")
        pick = pick_monthly_release(run_date, _read_tags_file(tags_file))
        return pick, "github"

    if src == "supabase":
        tags = sb_tags if sb_tags is not None else _supabase_tags()
        if not tags:
            raise ValueError("no committed monthly tags in Supabase")
        pick = pick_monthly_release(run_date, tags)
        return pick, "supabase"

    if src == "auto":
        if monthly_read_uses_supabase_primary(stage):
            if sb_tags is not None:
                tags = sb_tags
            else:
                try:
                    tags = _supabase_tags()
                except Exception:
                    if not monthly_read_allows_github_fallback(stage):
                        raise
                    tags = []
            if tags:
                try:
                    pick = pick_monthly_release(run_date, tags)
                    if (
                        monthly_read_allows_github_fallback(stage)
                        and tags_file is not None
                        and tags_file.is_file()
                    ):
                        gh_tags = _read_tags_file(tags_file)
                        if gh_tags:
                            gh_pick = pick_monthly_release(run_date, gh_tags)
                            if (
                                gh_pick.universe_resolution == "time_series_ok"
                                and _monthly_tag_sort_key(gh_pick.tag) > _monthly_tag_sort_key(pick.tag)
                            ):
                                return gh_pick, "github_fallback"
                    if pick.universe_resolution == "time_series_ok" or not monthly_read_allows_github_fallback(stage):
                        return pick, "supabase"
                except ValueError:
                    pass
            if monthly_read_allows_github_fallback(stage):
                if tags_file is None:
                    raise ValueError("--tags-file required for auto github fallback")
                pick = pick_monthly_release(run_date, _read_tags_file(tags_file))
                return pick, "github_fallback"
            raise ValueError("no monthly tags available from Supabase")
        if tags_file is None:
            raise ValueError("--tags-file required for source=auto at stage 4a")
        pick = pick_monthly_release(run_date, _read_tags_file(tags_file))
        return pick, "github"

    raise ValueError(f"invalid --source: {source}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resolve monthly tag for run_date (Phase 4).")
    parser.add_argument("--run-date", required=True)
    parser.add_argument(
        "--source",
        default="auto",
        choices=("auto", "github", "supabase"),
        help="4a: github; 4b/4c: auto (Supabase primary)",
    )
    parser.add_argument("--tags-file", type=Path, default=None)
    parser.add_argument("--phase4-rollout-stage", default=None)
    args = parser.parse_args(argv)

    try:
        run_d = date.fromisoformat(args.run_date.strip())
    except ValueError:
        print(f"error: invalid --run-date: {args.run_date}", file=sys.stderr)
        sys.exit(1)

    stage = resolve_phase4_rollout_stage(
        cli_override=args.phase4_rollout_stage,
        mapping=load_mapping(),
    )

    try:
        pick, resolve_source = resolve_monthly_tag(
            run_d,
            source=args.source,
            tags_file=args.tags_file,
            phase4_stage=stage,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    print(f"monthly_tag={pick.tag}")
    print(f"universe_resolution={pick.universe_resolution}")
    print(f"resolution_reason={pick.reason}")
    print(f"monthly_resolve_source={resolve_source}")
    _append_github_output(gh_out, "monthly_tag", pick.tag)
    _append_github_output(gh_out, "universe_resolution", pick.universe_resolution)
    _append_github_output(gh_out, "resolution_reason", _escape_kv(pick.reason))
    _append_github_output(gh_out, "monthly_resolve_source", resolve_source)


if __name__ == "__main__":
    main()
