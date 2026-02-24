"""
fetch_jpx_list の Pure 関数のテスト。
形式判定（detect_excel_format）と Excel→CSV 変換（excel_content_to_csv_bytes）を検証する。
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from stockradar.jobs.fetch_jpx_list import (
    detect_excel_format,
    excel_content_to_csv_bytes,
)

# 形式判定用マジックバイト
_MAGIC_XLSX = b"PK"
_MAGIC_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1"


def test_detect_excel_format_xlsx() -> None:
    """PK で始まる場合は xlsx。"""
    assert detect_excel_format(_MAGIC_XLSX + b"rest") == "xlsx"


def test_detect_excel_format_xls() -> None:
    """OLE2 で始まる場合は xls。"""
    assert detect_excel_format(_MAGIC_XLS + b"rest") == "xls"


def test_detect_excel_format_invalid_raises() -> None:
    """未対応の形式では RuntimeError。"""
    with pytest.raises(RuntimeError, match="Excel形式ではありません"):
        detect_excel_format(b"invalid")


def test_detect_excel_format_html_raises() -> None:
    """HTML の場合は RuntimeError でメッセージに HTML/XML と出る。"""
    with pytest.raises(RuntimeError, match="HTML/XML"):
        detect_excel_format(b"  <!DOCTYPE html>")


def test_excel_content_to_csv_bytes_xlsx() -> None:
    """xlsx バイ列を CSV バイ列に変換できる。"""
    df = pd.DataFrame({"コード": ["7203"], "銘柄名": ["トヨタ"]})
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    content = buf.getvalue()

    result = excel_content_to_csv_bytes(content, "xlsx")
    assert isinstance(result, bytes)
    decoded = result.decode("utf-8-sig")
    assert "コード" in decoded
    assert "銘柄名" in decoded
    assert "7203" in decoded
    assert "トヨタ" in decoded
