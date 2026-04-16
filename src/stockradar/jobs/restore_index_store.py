"""Extract index_store.zip into data/cache/yf_index/."""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from stockradar.config import get_index_store_archive_zip_path, get_yf_index_cache_dir


def restore_index_store(base_dir: Path | None = None) -> None:
    base = base_dir or Path.cwd()
    archive_zip = get_index_store_archive_zip_path(base)
    store_dir = get_yf_index_cache_dir(base)

    if archive_zip.exists():
        print(f"restore: {archive_zip} -> {store_dir}", file=sys.stderr)
        if store_dir.exists():
            shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_zip, "r") as zf:
                zf.extractall(store_dir)
            print(f"done: {store_dir}", file=sys.stderr)
        except Exception as e:
            print(f"error: unzip failed: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"warn: no zip: {archive_zip} (empty dir)", file=sys.stderr)
        if store_dir.exists():
            shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Restore yf_index from zip archive.")
    parser.parse_args(argv)
    try:
        restore_index_store()
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
