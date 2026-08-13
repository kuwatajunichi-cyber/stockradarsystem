"""Convert UTF-16-LE text files to UTF-8 (strip BOM). One-shot repair for corrupted commits."""
from __future__ import annotations

import sys
from pathlib import Path

TEXT_SUFFIXES = {".py", ".json", ".yml", ".yaml", ".sql", ".md", ".toml", ".txt", ".sh"}


def is_utf16_le(raw: bytes) -> bool:
    if len(raw) < 4:
        return False
    return raw.count(0) > len(raw) // 4


def convert_file(path: Path, dry_run: bool = False) -> bool:
    raw = path.read_bytes()
    if not is_utf16_le(raw):
        return False
    text = raw.decode("utf-16-le")
    if not dry_run:
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"fixed: {path}")
    return True


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if paths:
        targets = [Path(p) for p in paths]
    else:
        repo = Path(__file__).resolve().parents[2]
        targets = []
        for p in repo.rglob("*"):
            if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
                continue
            if any(x in p.parts for x in (".git", "node_modules", ".egg-info", "__pycache__")):
                continue
            targets.append(p)
    fixed = sum(1 for p in targets if convert_file(p, dry_run=dry_run))
    print(f"converted {fixed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
