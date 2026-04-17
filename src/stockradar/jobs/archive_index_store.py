"""Zip yf_index store to data/cache/index_store_archive/index_store.zip."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from stockradar.config import get_index_store_archive_zip_path, get_yf_index_cache_dir


def archive_index_store(base_dir: Path | None = None) -> None:
    base = base_dir or Path.cwd()
    store_dir = get_yf_index_cache_dir(base)
    archive_zip = get_index_store_archive_zip_path(base)
    archive_zip.parent.mkdir(parents=True, exist_ok=True)

    if archive_zip.exists():
        archive_zip.unlink()

    if not store_dir.exists():
        print(f"warn: index store missing: {store_dir} (empty zip)", file=sys.stderr)
        with zipfile.ZipFile(archive_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            pass
        print(f"empty zip: {archive_zip}", file=sys.stderr)
        return

    print(f"zip: {store_dir} -> {archive_zip}", file=sys.stderr)
    try:
        with zipfile.ZipFile(archive_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in store_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(store_dir)
                    zf.write(file_path, arcname)
        print(f"done: {archive_zip} ({archive_zip.stat().st_size} bytes)", file=sys.stderr)
    except Exception as e:
        print(f"error: zip failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Archive yf_index store to zip.")
    parser.parse_args(argv)
    try:
        archive_index_store()
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
