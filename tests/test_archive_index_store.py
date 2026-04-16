from pathlib import Path

import shutil

from stockradar.config import get_index_store_archive_zip_path, get_yf_index_cache_dir
from stockradar.jobs.archive_index_store import archive_index_store
from stockradar.jobs.restore_index_store import restore_index_store


def test_archive_restore_index_roundtrip(tmp_path: Path) -> None:
    store = get_yf_index_cache_dir(tmp_path)
    store.mkdir(parents=True)
    (store / "sample.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    archive_index_store(tmp_path)
    zip_path = get_index_store_archive_zip_path(tmp_path)
    assert zip_path.is_file()

    shutil.rmtree(store)
    restore_index_store(tmp_path)
    assert (store / "sample.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"