"""
Resolve core CSV for daily.yml: patched Actions cache or monthly release.

Subcommands:
  select: resolve MONTHLY_TAG, list caches, pick key, write state JSON + GITHUB_OUTPUT (no restore)
  materialize: after optional cache restore, copy patched CSV or gh release download to staging
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from stockradar.jobs.core_csv_selection import (
    PATCHED_KEY_PREFIX,
    count_unparseable_patched_prefixed_keys,
    select_patched_cache_key,
)
from stockradar.jobs.patch_universe_daily import MANIFEST_FILENAME as PATCH_MANIFEST_NAME
from stockradar.universe.monthly_release_pick import pick_monthly_release

STATE_FILENAME = ".resolve_core_state.json"
CORE_CSV_NAME = "equity_domestic_core_with_name.csv"
QUALITY_JSON_NAME = "core_selection.json"


def _append_github_output(path: str | None, key: str, value: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def _escape_kv(s: str) -> str:
    return s.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def list_action_cache_entries(repo: str) -> list[tuple[str, str]]:
    """Paginate GitHub Actions caches via gh api; return (key, ref) per entry.

    ``ref`` is the branch/tag ref GitHub associates with the cache (e.g. ``refs/heads/main``).
    ``actions/cache/restore`` only restores entries visible for the current workflow ref scope;
    callers should filter by allowed refs before selecting a key.
    """
    entries: list[tuple[str, str]] = []
    page = 1
    while True:
        proc = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/caches?per_page=100&page={page}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"error: gh api caches failed: {proc.stderr or proc.stdout}", file=sys.stderr)
            sys.exit(1)
        payload = json.loads(proc.stdout or "{}")
        batch = payload.get("actions_caches") or []
        if not batch:
            break
        for ent in batch:
            k = ent.get("key")
            if not isinstance(k, str) or not k:
                continue
            r = ent.get("ref")
            ref_s = r.strip() if isinstance(r, str) else ""
            entries.append((k, ref_s))
        if len(batch) < 100:
            break
        page += 1
        if page > 500:
            print("error: actions caches pagination exceeded safety cap (500 pages)", file=sys.stderr)
            sys.exit(1)
    return entries


def cache_keys_for_allowed_refs(
    entries: list[tuple[str, str]],
    allowed_refs: frozenset[str],
) -> list[str]:
    """Keep cache keys whose ``ref`` is restorable for this workflow run."""
    if not allowed_refs:
        return [k for k, _r in entries]
    return [k for k, r in entries if r in allowed_refs]


def run_select(
    args: argparse.Namespace,
    *,
    list_cache_entries: Callable[[str], list[tuple[str, str]]] | None = None,
) -> None:
    repo = args.repo.strip()
    if not repo:
        print("error: --repo or GITHUB_REPOSITORY is required", file=sys.stderr)
        sys.exit(1)

    try:
        run_d = date.fromisoformat(args.run_date.strip())
    except ValueError:
        print(f"error: invalid --run-date {args.run_date}", file=sys.stderr)
        sys.exit(1)

    if not args.tags_file.is_file():
        print(f"error: tags file not found: {args.tags_file}", file=sys.stderr)
        sys.exit(1)

    tag_lines = [
        ln.strip()
        for ln in args.tags_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    try:
        pick = pick_monthly_release(run_d, tag_lines)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    allowed = frozenset(
        x.strip()
        for x in (getattr(args, "patched_cache_allowed_ref", None) or [])
        if isinstance(x, str) and x.strip()
    )
    lister = list_cache_entries or list_action_cache_entries
    cache_keys = cache_keys_for_allowed_refs(lister(repo), allowed)
    bad_pref = count_unparseable_patched_prefixed_keys(cache_keys)
    if bad_pref:
        print(
            f"warning: {bad_pref} action cache key(s) start with {PATCHED_KEY_PREFIX!r} "
            "but are not parseable as universe-patched-<MONTHLY_TAG>-<YYYY-MM-DD>; "
            "they are ignored for patched-universe selection",
            file=sys.stderr,
        )
    chosen = select_patched_cache_key(cache_keys, monthly_tag=pick.tag, run_date=run_d)

    state = {
        "monthly_tag": pick.tag,
        "universe_resolution": pick.universe_resolution,
        "resolution_reason": pick.reason,
        "run_date": run_d.isoformat(),
        "patched_cache_key": chosen,
    }
    state_path: Path = args.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    need_restore = "true" if chosen else "false"
    print(f"need_patched_restore={need_restore}")
    print(f"patched_cache_key={chosen or ''}")
    print(f"monthly_tag={pick.tag}")
    _append_github_output(gh_out, "need_patched_restore", need_restore)
    _append_github_output(gh_out, "patched_cache_key", chosen or "")
    _append_github_output(gh_out, "monthly_tag", pick.tag)
    _append_github_output(gh_out, "universe_resolution", pick.universe_resolution)
    _append_github_output(gh_out, "resolution_reason", _escape_kv(pick.reason))


def _write_quality(
    path: Path,
    *,
    core_source: str,
    delisted_patch_applied: bool,
    selected_cache_key: str | None,
    monthly_tag: str,
    run_date: str,
    quality_tier: str,
    universe_resolution: str,
    resolution_reason: str,
) -> None:
    doc = {
        "core_source": core_source,
        "delisted_patch_applied": delisted_patch_applied,
        "selected_cache_key": selected_cache_key,
        "MONTHLY_TAG": monthly_tag,
        "run_date": run_date,
        "quality_tier": quality_tier,
        "universe_resolution": universe_resolution,
        "resolution_reason": resolution_reason,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_gh_release_download(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def run_materialize(
    args: argparse.Namespace,
    *,
    gh_release_download: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> None:
    repo = args.repo.strip()
    if not repo:
        print("error: --repo or GITHUB_REPOSITORY is required", file=sys.stderr)
        sys.exit(1)

    state_path = args.staging_dir / STATE_FILENAME
    if not state_path.is_file():
        print(f"error: state file missing: {state_path}", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    monthly_tag = str(state.get("monthly_tag") or "").strip()
    run_date = str(state.get("run_date") or "").strip()
    patched_key = state.get("patched_cache_key")
    uv_res = str(state.get("universe_resolution") or "")
    reason = str(state.get("resolution_reason") or "")

    if not monthly_tag or not run_date:
        print("error: invalid state (monthly_tag/run_date)", file=sys.stderr)
        sys.exit(1)

    args.staging_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.staging_dir / CORE_CSV_NAME
    out_quality = args.staging_dir / QUALITY_JSON_NAME
    if out_csv.exists():
        out_csv.unlink()
    if out_quality.exists():
        out_quality.unlink()

    patched_csv = args.patched_dir / CORE_CSV_NAME
    patched_manifest = args.patched_dir / PATCH_MANIFEST_NAME

    patched_key_str = patched_key.strip() if isinstance(patched_key, str) else ""
    want_patched = patched_key_str != ""
    patched_files_ready = want_patched and patched_csv.is_file() and patched_manifest.is_file()

    if want_patched and not patched_files_ready:
        print(
            f"warning: patched cache key={patched_key_str!r} was selected but "
            f"expected files are missing under {args.patched_dir} "
            "(eviction, restore miss, or race); using monthly release CSV "
            "(degraded_without_delisted_patch).",
            file=sys.stderr,
        )

    if patched_files_ready:
        manifest_tag: str | None = None
        try:
            man = json.loads(patched_manifest.read_text(encoding="utf-8"))
            manifest_tag = (man.get("chosen_monthly_tag") or man.get("base_release") or "").strip() or None
        except json.JSONDecodeError:
            manifest_tag = None
        if manifest_tag != monthly_tag:
            print(
                f"error: patched manifest monthly mismatch: manifest={manifest_tag!r} expected={monthly_tag!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        shutil.copy2(patched_csv, out_csv)
        shutil.copy2(patched_manifest, args.staging_dir / PATCH_MANIFEST_NAME)
        _write_quality(
            out_quality,
            core_source="patched_cache",
            delisted_patch_applied=True,
            selected_cache_key=patched_key_str,
            monthly_tag=monthly_tag,
            run_date=run_date,
            quality_tier="full",
            universe_resolution=uv_res,
            resolution_reason=reason,
        )
        print(f"core_csv={out_csv}")
        return

    tmp_release = args.staging_dir / "_monthly_dl"
    if tmp_release.exists():
        shutil.rmtree(tmp_release)
    tmp_release.mkdir(parents=True, exist_ok=True)
    dl = gh_release_download or _default_gh_release_download
    proc = dl(
        [
            "gh",
            "release",
            "download",
            monthly_tag,
            "--pattern",
            CORE_CSV_NAME,
            "--dir",
            str(tmp_release),
            "--repo",
            repo,
        ]
    )
    if proc.returncode != 0:
        print(f"error: gh release download failed: {proc.stderr or proc.stdout}", file=sys.stderr)
        sys.exit(1)
    src = tmp_release / CORE_CSV_NAME
    if not src.is_file():
        print(f"error: downloaded csv missing: {src}", file=sys.stderr)
        sys.exit(1)
    shutil.move(str(src), str(out_csv))
    shutil.rmtree(tmp_release, ignore_errors=True)

    _write_quality(
        out_quality,
        core_source="monthly_fallback",
        delisted_patch_applied=False,
        selected_cache_key=None,
        monthly_tag=monthly_tag,
        run_date=run_date,
        quality_tier="degraded_without_delisted_patch",
        universe_resolution=uv_res,
        resolution_reason=reason,
    )
    print(f"core_csv={out_csv}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resolve core CSV for daily indicators workflow.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sel = sub.add_parser("select", help="Resolve monthly tag and select patched cache key")
    p_sel.add_argument("--run-date", required=True)
    p_sel.add_argument("--tags-file", type=Path, required=True)
    p_sel.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "").strip())
    p_sel.add_argument(
        "--patched-cache-allowed-ref",
        action="append",
        dest="patched_cache_allowed_ref",
        default=None,
        help=(
            "Restrict patched-cache key listing to caches tied to this ref (repeatable). "
            "In GitHub Actions pass the workflow ref and default branch ref "
            "(e.g. refs/heads/feature-x and refs/heads/main) so restore can hit the entry."
        ),
    )
    p_sel.add_argument(
        "--state-path",
        type=Path,
        default=Path("data/universe/jpx/core_selected_staging") / STATE_FILENAME,
    )

    p_mat = sub.add_parser("materialize", help="Write core CSV + quality JSON to staging")
    p_mat.add_argument("--staging-dir", type=Path, default=Path("data/universe/jpx/core_selected_staging"))
    p_mat.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "").strip())
    p_mat.add_argument("--patched-dir", type=Path, default=Path("data/universe/jpx/patched_cache"))

    args = parser.parse_args(argv)
    if args.cmd == "select":
        run_select(args)
    elif args.cmd == "materialize":
        run_materialize(args)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
