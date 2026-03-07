from __future__ import annotations

from datetime import date

from stockradar.sources.external_events import (
    fetch_kabutan_news_for_month,
    fetch_tdnet_disclosures_for_date,
)


class _DummyResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _DummySession:
    def __init__(self, route: dict[str, _DummyResp]) -> None:
        self.route = route

    def get(self, url, params=None, timeout=0):  # noqa: ANN001
        if "kabutan.jp/stock/news" in url:
            return self.route["kabutan"]
        if "I_list_001_20260306.html" in url:
            return self.route["tdnet1"]
        if "I_list_002_20260306.html" in url:
            return self.route["tdnet2"]
        return _DummyResp("", status_code=404)


def test_fetch_kabutan_news_for_month_parses_rows() -> None:
    html = """
    <html><body>
      <table>
        <tr><th>x</th></tr>
        <tr>
          <td>26/03/06 16:30</td>
          <td><a href="/stock/news?code=7203&b=n202603060001">自己株式の取得に関するお知らせ</a></td>
        </tr>
      </table>
    </body></html>
    """
    session = _DummySession(route={"kabutan": _DummyResp(html), "tdnet1": _DummyResp(""), "tdnet2": _DummyResp("", 404)})
    events = fetch_kabutan_news_for_month(code="7203", yyyymm00="20260300", session=session)
    assert len(events) == 1
    assert events[0].code == "7203"
    assert events[0].source == "kabutan"
    assert events[0].source_category == ""
    assert events[0].event_type in {"share_buyback", "other"}


def test_fetch_tdnet_disclosures_for_date_parses_rows() -> None:
    html1 = """
    <html><body><table>
      <tr>
        <td>16:30</td><td>72030</td><td>トヨタ自</td>
        <td><a href="140120260306577638.pdf">自己株式取得に係る事項の変更等に関するお知らせ</a></td>
      </tr>
    </table></body></html>
    """
    # 次ページは404で終了
    session = _DummySession(
        route={
            "kabutan": _DummyResp(""),
            "tdnet1": _DummyResp(html1),
            "tdnet2": _DummyResp("", status_code=404),
        }
    )
    events = fetch_tdnet_disclosures_for_date(date(2026, 3, 6), session=session, max_pages=2)
    assert len(events) == 1
    assert events[0].source == "tdnet"
    assert events[0].code == "7203"
    assert events[0].source_category == ""
