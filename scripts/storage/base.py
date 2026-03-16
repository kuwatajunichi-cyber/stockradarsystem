"""
ストレージ抽象レイヤ。Drive 以外のストレージ（R2, Dropbox）を統一インターフェースで扱う。
path は論理ディレクトリ（末尾 / 付き）。各 Adapter は key = base_prefix + path + name で結合する。
"""
from __future__ import annotations

from typing import Protocol


class StorageAdapter(Protocol):
    """日次成果物のアップロード・削除の抽象。R2 / Dropbox 等が実装する。"""

    def upload_file(
        self,
        path: str,
        name: str,
        content: bytes,
        mime_type: str = "text/plain",
    ) -> str:
        """
        指定論理パスにファイルをアップロードする。
        path: 末尾 / を含む論理ディレクトリ（例: 0011_work/2026-03/2026-03-17/）
        戻り値: そのストレージ内での参照用 ID または key
        """
        ...

    def delete_older_than(self, cutoff_ym: str) -> None:
        """
        cutoff_ym より古い月の成果物を削除する。
        cutoff_ym: "YYYY-MM" 形式。これより小さい YYYY-MM を削除対象とする。
        """
        ...
