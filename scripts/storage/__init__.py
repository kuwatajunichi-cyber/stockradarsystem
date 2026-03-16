"""ストレージ抽象と R2 / Dropbox Adapter。"""
from scripts.storage.base import StorageAdapter
from scripts.storage.paths import (
    PAID_PREFIX,
    WORK_PREFIX,
    build_day_path,
    build_month_path,
)
from scripts.storage.r2_client import R2StorageAdapter
from scripts.storage.dropbox_client import DropboxStorageAdapter

__all__ = [
    "StorageAdapter",
    "R2StorageAdapter",
    "DropboxStorageAdapter",
    "build_month_path",
    "build_day_path",
    "WORK_PREFIX",
    "PAID_PREFIX",
]
