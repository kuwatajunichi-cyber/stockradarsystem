from __future__ import annotations

from datetime import date

from stockradar.sources.name_aliases_media import (
    FetchPolicy,
    MediaStats,
    fetch_kabutan_aliases_for_code,
    fetch_nikkei_aliases_for_code,
    fetch_reuters_aliases_for_code,
    fetch_tdnet_issuer_counts,
)


class _DummyResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


class _DummySession:
    def __init__(self, route: dict[str, list[_DummyResp]]) -> None:
        self.route = route
        self.count: dict[str, int] = {}

    def get(self, url, params=None, timeout=0):  # noqa: ANN001
        key = str(url)
        if params:
            if "code" in params:
                key = f"{key}?code={params['code']}"
        vals = self.route.get(key, [])
        idx = self.count.get(key, 0)
        self.count[key] = idx + 1
        if not vals:
            return _DummyResp("", status_code=404)
        if idx >= len(vals):
            return vals[-1]
        return vals[idx]


def test_media_extractors_parse_kabutan_nikkei_reuters() -> None:
    session = _DummySession(
        {
            "https://kabutan.jp/stock/?code=7203": [
                _DummyResp("<html><head><title>トヨタ自動車（トヨタ）【7203】株の基本情報</title></head></html>")
            ],
            "https://www.nikkei.com/nkd/company/?scode=7203": [
                _DummyResp("<html><head><title>【トヨタ自動車】業績・財務 最新ニュース[7203] | 日本経済新聞</title></head></html>")
            ],
            "https://jp.reuters.com/markets/companies/7203.T": [
                _DummyResp("<html><body><h1>Toyota Motor Corp</h1></body></html>")
            ],
        }
    )
    policy = FetchPolicy(sleep_ms=0, sleep_jitter_ms=0, retry_max=1, retry_backoff_ms=[0])
    host_next: dict[str, float] = {}
    stats_k = MediaStats()
    stats_n = MediaStats()
    stats_r = MediaStats()
    kab = fetch_kabutan_aliases_for_code(
        "7203", session=session, policy=policy, stats=stats_k, host_next_ts=host_next
    )
    nik = fetch_nikkei_aliases_for_code(
        "7203", session=session, policy=policy, stats=stats_n, host_next_ts=host_next
    )
    reu = fetch_reuters_aliases_for_code(
        "7203", session=session, policy=policy, stats=stats_r, host_next_ts=host_next
    )
    assert "トヨタ" in kab
    assert "トヨタ自動車" in nik
    assert "Toyota Motor Corp" in reu
    assert "Toyota Motor" in reu


def test_media_retry_success_counts_retry_and_success() -> None:
    session = _DummySession(
        {
            "https://www.nikkei.com/nkd/company/?scode=9432": [
                _DummyResp("", status_code=503),
                _DummyResp("<html><head><title>【NTT】業績・財務 最新ニュース[9432] | 日本経済新聞</title></head></html>"),
            ]
        }
    )
    stats = MediaStats()
    policy = FetchPolicy(sleep_ms=0, sleep_jitter_ms=0, retry_max=2, retry_backoff_ms=[0, 0])
    out = fetch_nikkei_aliases_for_code("9432", session=session, policy=policy, stats=stats, host_next_ts={})
    assert "NTT" in out
    assert stats.requests == 2
    assert stats.retry == 1
    assert stats.success == 1
    assert stats.fail == 0


def test_tdnet_issuer_counts_collects_and_normalizes_code() -> None:
    html = """
    <html><body><table>
      <tr><td>15:00</td><td>72030</td><td>Ｇ－トヨタ自動車</td><td><a href='x.pdf'>開示</a></td></tr>
      <tr><td>15:10</td><td>72030</td><td>Ｇ－トヨタ自動車</td><td><a href='y.pdf'>開示2</a></td></tr>
      <tr><td>15:20</td><td>94320</td><td>ＮＴＴ</td><td><a href='z.pdf'>開示3</a></td></tr>
    </table></body></html>
    """
    session = _DummySession(
        {
            "https://www.release.tdnet.info/inbs/I_list_001_20260306.html": [_DummyResp(html)],
            "https://www.release.tdnet.info/inbs/I_list_002_20260306.html": [_DummyResp("", status_code=404)],
        }
    )
    stats = MediaStats()
    policy = FetchPolicy(sleep_ms=0, sleep_jitter_ms=0, retry_max=1, retry_backoff_ms=[0])
    out = fetch_tdnet_issuer_counts(
        codes={"7203", "9432"},
        start_date=date(2026, 3, 6),
        end_date=date(2026, 3, 6),
        session=session,
        policy=policy,
        stats=stats,
        host_next_ts={},
        max_pages=2,
    )
    assert out["7203"]["トヨタ自動車"] == 2
    assert out["9432"]["NTT"] == 1

