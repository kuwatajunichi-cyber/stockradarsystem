"""
jpx_resolver の Pure 関数のテスト。
extract_excel_urls_from_html を HTML 文字列のみで検証する。
"""
from __future__ import annotations

import pytest

from stockradar.sources.jpx_resolver import extract_excel_urls_from_html


def test_extract_excel_urls_from_html_empty() -> None:
    """リンクが無い HTML では空リスト。"""
    html = "<html><body><p>No links</p></body></html>"
    assert extract_excel_urls_from_html(html, "https://www.jpx.co.jp/page/") == []


def test_extract_excel_urls_from_html_finds_xlsx() -> None:
    """同一サイトの .xlsx リンクを絶対 URL で返す。"""
    html = """
    <html><body>
    <a href="/markets/statistics-equities/misc/01.xlsx">Download</a>
    <a href="https://www.jpx.co.jp/other/file.xls">XLS</a>
    </body></html>
    """
    base = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
    urls = extract_excel_urls_from_html(html, base)
    assert len(urls) == 2
    assert urls[0] == "https://www.jpx.co.jp/markets/statistics-equities/misc/01.xlsx"
    assert urls[1] == "https://www.jpx.co.jp/other/file.xls"


def test_extract_excel_urls_from_html_ignores_other_domain() -> None:
    """他ドメインの .xlsx は含めない。"""
    html = """
    <html><body>
    <a href="https://other.example.com/file.xlsx">External</a>
    <a href="/local.xlsx">Local</a>
    </body></html>
    """
    base = "https://www.jpx.co.jp/page.html"
    urls = extract_excel_urls_from_html(html, base)
    assert urls == ["https://www.jpx.co.jp/local.xlsx"]


def test_extract_excel_urls_from_html_ignores_non_excel_links() -> None:
    """ .xls / .xlsx 以外のリンクは無視。"""
    html = """
    <html><body>
    <a href="/file.pdf">PDF</a>
    <a href="/file.csv">CSV</a>
    <a href="/file.xlsx">Excel</a>
    </body></html>
    """
    base = "https://www.jpx.co.jp/page.html"
    urls = extract_excel_urls_from_html(html, base)
    assert urls == ["https://www.jpx.co.jp/file.xlsx"]
