#!/usr/bin/env python3
"""
Delete old GitHub Actions artifacts by prefix rules (config-driven).

Contract:
  - Exit 0: completed (including dry-run / no matches).
  - Exit 1: config error, gh api failures, or candidates exceed per-rule max_delete.
  - Does not log secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from stockradar.jobs.cleanup_artifacts_lib import CleanupRule, cutoff_epoch_utc, should_delete_artifact


def _load_rules(path: Path) -> list[CleanupRule]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules_raw = raw.get("rules") or []
    out: list[CleanupRule] = []
    for i, ent in enumerate(rules_raw):
        if not isinstance(ent, dict):
            raise ValueError(f"rules[{i}] must be a mapping")
        out.append(
            CleanupRule(
                prefix=str(ent["prefix"]),
                keep_days=int(ent["keep_days"]),
                enabled=bool(ent.get("enabled", True)),
                max_delete=int(ent.get("max_delete", 200)),
            )
        )
    return out


def _gh_api_json(repo: str, path: str) -> dict:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/{path}"],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        print(f"error: gh api failed: {proc.stderr or proc.stdout}", file=sys.stderr)
        sys.exit(1)
    return json.loads(proc.stdout or "{}")


def _list_all_artifacts(repo: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        payload = _gh_api_json(repo, f"actions/artifacts?per_page=100&page={page}")
        batch = payload.get("artifacts") or []
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 500:
            print("error: artifacts pagination exceeded safety cap", file=sys.stderr)
            sys.exit(1)
    return items


def _delete_artifact(repo: str, artifact_id: int) -> bool:
    proc = subprocess.run(
        ["gh", "api", "-X", "DELETE", f"repos/{repo}/actions/artifacts/{artifact_id}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cleanup GitHub Actions artifacts by config rules.")
    parser.add_argument("--config", type=Path, default=Path("config/cleanup_artifacts.yaml"))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "").strip())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.repo:
        print("error: --repo or GITHUB_REPOSITORY required", file=sys.stderr)
        sys.exit(1)
    if not args.config.is_file():
        print(f"error: config not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    try:
        rules = _load_rules(args.config)
    except (KeyError, TypeError, ValueError) as e:
        print(f"error: invalid config: {e}", file=sys.stderr)
        sys.exit(1)

    artifacts = _list_all_artifacts(args.repo)
    to_delete: list[tuple[int, str, str, str]] = []
    seen: set[int] = set()
    for rule in rules:
        if not rule.enabled:
            continue
        cut = cutoff_epoch_utc(keep_days=rule.keep_days)
        picked: list[tuple[int, str, str]] = []
        for a in artifacts:
            if a.get("expired") is True:
                continue
            name = str(a.get("name") or "")
            created = str(a.get("created_at") or "")
            aid = a.get("id")
            if not isinstance(aid, int):
                continue
            if aid in seen:
                continue
            if should_delete_artifact(name, created, prefix=rule.prefix, cutoff_epoch=cut):
                picked.append((aid, name, created))
        if len(picked) > rule.max_delete:
            print(
                f"error: rule prefix={rule.prefix!r} candidates={len(picked)} exceed max_delete={rule.max_delete}",
                file=sys.stderr,
            )
            sys.exit(1)
        for aid, name, created in picked:
            seen.add(aid)
            to_delete.append((aid, name, created, rule.prefix))

    print(f"repo={args.repo}")
    print(f"dry_run={args.dry_run}")
    print(f"candidates={len(to_delete)}")
    for aid, name, created, prefix in to_delete:
        print(f"- id={aid} name={name} created_at={created} rule_prefix={prefix}")

    if args.dry_run:
        print("dry-run: no artifacts deleted.")
        return

    ok = 0
    fail = 0
    for aid, name, _, _ in to_delete:
        if _delete_artifact(args.repo, aid):
            ok += 1
            print(f"deleted id={aid} name={name}")
        else:
            fail += 1
            print(f"failed id={aid} name={name}", file=sys.stderr)
    print(f"cleanup_result: success={ok} fail={fail}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
