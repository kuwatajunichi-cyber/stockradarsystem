"""
jpx_delisted の Pure 関数と Fake 注入のテスト。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stockradar.sources.jpx_delisted import (
    apply_delisted_patch,
    fetch_delisted_codes,
    parse_delisted_table,
)


def test_parse_delisted_table_empty() -> None:
    """表がない HTML では空リスト。"""
    html = "<html><body><p>No table</p></body></html>"
    assert parse_delisted_table(html, "https://www.jpx.co.jp/listing/stocks/delisted/index.html") == []


def test_parse_delisted_table_extracts_code_and_date() -> None:
    """表からコード（4桁ゼロ埋め）と上場廃止日を抽出する。"""
    html = """
    <html><body>
    <table>
    <tr><th>上場廃止日</th><th>銘柄名</th><th>コード</th><th>市場区分</th><th>理由</th></tr>
    <tr><td>2026/03/25</td><td>ダイワ通信</td><td>7116</td><td>スタンダード</td><td>買収</td></tr>
    <tr><td>2026/02/26</td><td>ライトオン</td><td>7445</td><td>スタンダード</td><td>株式交換</td></tr>
    </tr>
    </table>
    </body></html>
    """
    base = "https://www.jpx.co.jp/listing/stocks/delisted/index.html"
    result = parse_delisted_table(html, base)
    assert len(result) == 2
    assert result[0] == ("7116", date(2026, 3, 25))
    assert result[1] == ("7445", date(2026, 2, 26))


def test_parse_delisted_table_normalizes_code() -> None:
    """コードは数字のみなら4桁ゼロ埋め。"""
    html = """
    <html><body>
    <table>
    <tr><td>2026/01/05</td><td>例</td><td>123</td><td>プライム</td><td>理由</td></tr>
    </table>
    </body></html>
    """
    result = parse_delisted_table(html, "https://example.com/")
    assert result == [("0123", date(2026, 1, 5))]


def test_apply_delisted_patch_removes_codes() -> None:
    """delisted_codes に含まれる code の行を削除する。"""
    df = pd.DataFrame({"code": ["7116", "7203", "7445"], "name": ["A", "B", "C"]})
    removed = apply_delisted_patch(df, {"7116", "7445"})
    assert list(removed["code"]) == ["7203"]
    assert len(removed) == 1


def test_apply_delisted_patch_empty_delisted() -> None:
    """除外集合が空なら全行残る。"""
    df = pd.DataFrame({"code": ["7203"], "name": ["B"]})
    assert len(apply_delisted_patch(df, set())) == 1


def test_apply_delisted_patch_requires_code_column() -> None:
    """code 列が無いと ValueError。"""
    df = pd.DataFrame({"id": [1], "name": ["x"]})
    with pytest.raises(ValueError, match="code 列がありません"):
        apply_delisted_patch(df, set())


class FakeFetcher:
    """固定 HTML を返す HttpFetcher。"""

    def __init__(self, html: str) -> None:
        self.html = html

    def get(self, url: str) -> str:
        return self.html


def test_fetch_delisted_codes_with_fake_fetcher() -> None:
    """Fake で HTML を渡すと、run_date 以前かつ lookback 内のコードのみ返す。"""
    html = """
    <html><body>
    <table>
    <tr><td>2026/02/15</td><td>X</td><td>7116</td><td>S</td><td>R</td></tr>
    <tr><td>2026/01/10</td><td>Y</td><td>7203</td><td>P</td><td>R</td></tr>
    <tr><td>2025/11/01</td><td>Z</td><td>7445</td><td>S</td><td>R</td></tr>
    </table>
    </body></html>
    """
    fetcher = FakeFetcher(html)
    # run_date=2026-02-20, lookback=2 → 2025/12/01 以降のみ。7445 は 2025/11 なので除外。
    codes = fetch_delisted_codes(
        date(2026, 2, 20),
        lookback_months=2,
        fetcher=fetcher,
    )
    assert codes == {"7116", "7203"}


def test_fetch_delisted_codes_future_dates_excluded() -> None:
    """廃止日が run_date より未来の行は含めない。"""
    html = """
    <html><body>
    <table>
    <tr><td>2026/03/25</td><td>X</td><td>7116</td><td>S</td><td>R</td></tr>
    </table>
    </body></html>
    """
    fetcher = FakeFetcher(html)
    codes = fetch_delisted_codes(date(2026, 2, 20), lookback_months=2, fetcher=fetcher)
    assert codes == set()


def test_fetch_delisted_codes_fetcher_exception_returns_empty() -> None:
    """fetcher が例外を出すと空集合で続行。"""

    class FailingFetcher:
        def get(self, url: str) -> str:
            raise OSError("network error")

    codes = fetch_delisted_codes(date(2026, 2, 20), lookback_months=2, fetcher=FailingFetcher())
    assert codes == set()
