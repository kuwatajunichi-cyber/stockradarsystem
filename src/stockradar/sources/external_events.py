"""
株探 / TDnet からイベント候補を取得する実験用ソース。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from stockradar.config import get_http_timeout

_KABUTAN_BASE = "https://kabutan.jp"
_TDNET_BASE = "https://www.release.tdnet.info/inbs"
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://kabutan.jp/",
}


@dataclass(frozen=True)
class ScrapedEvent:
    code: str
    source: str
    published_at: str
    title: str
    raw_text_short: str
    event_type: str
    event_polarity: str
    issuer_specificity: str
    novelty_level: str
    expected_impact_horizon: str
    confidence_base: float
    event_scope: str
    originality: str
    url: str
    source_category: str = ""
    has_xbrl: bool | None = None
    listing_exchange: str = ""
    has_update_history: bool | None = None


_RE_KABUTAN_DT = re.compile(r"^(?P<yy>\d{2})/(?P<mm>\d{2})/(?P<dd>\d{2})\s+(?P<hh>\d{2}):(?P<mi>\d{2})$")
_RE_CODE = re.compile(r"^[0-9A-Z]{4,5}$")


def _parse_kabutan_dt(value: str) -> datetime | None:
    m = _RE_KABUTAN_DT.match(value.strip())
    if not m:
        return None
    yy = int(m.group("yy"))
    year = 2000 + yy
    return datetime(
        year=year,
        month=int(m.group("mm")),
        day=int(m.group("dd")),
        hour=int(m.group("hh")),
        minute=int(m.group("mi")),
    )


def _parse_tdnet_dt(target_day: date, hhmm: str) -> datetime | None:
    parts = hhmm.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hh, mi = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return datetime(target_day.year, target_day.month, target_day.day, hh, mi)


def _norm_tdnet_code(code: str) -> str:
    c = code.strip().upper()
    if len(c) == 5 and c.endswith("0"):
        return c[:-1]
    return c


def _classify_event_type(title: str) -> str:
    t = title.lower()
    mapping = [
        (("業績予想の修正", "上方修正", "通期連結業績予想の修正"), "earnings_revision_up"),
        (("決算短信",), "earnings"),
        (("自己株式の取得", "自己株式取得", "自社株買い"), "share_buyback"),
        (("自己株式の消却",), "share_cancellation"),
        (("公開買付け", "tob"), "tob"),
        (("株式の取得（子会社化）", "子会社化"), "mna"),
        (("提携",), "partnership"),
        (("月次", "売上高速報", "kpi"), "monthly"),
        (("増配", "配当予想の修正"), "dividend_revision"),
        (("訂正", "開示事項の経過"), "followup"),
        (("レーティング",), "analyst_rating"),
        (("本日の【", "話題株", "市況"), "market_news"),
    ]
    for words, tag in mapping:
        if any(w in t for w in words):
            return tag
    return "other"


def _classify_novelty(title: str) -> str:
    t = title.lower()
    if "訂正" in t:
        return "low"
    if "経過" in t:
        return "followup"
    return "new"


def _classify_polarity(title: str) -> str:
    # 文脈依存が大きく誤判定リスクが高いため、現行PoCでは極性判定を行わない。
    # 将来、より高精度な手法（モデル/LLM等）を導入する際に再検討する。
    return "neutral"


def _classify_scope(source: str, title: str) -> tuple[str, str]:
    t = title.lower()
    if source == "tdnet":
        return "issuer", "company"
    if "本日の【" in title or "レーティング日報" in title or "話題株" in title:
        return "market", "low"
    return "issuer", "company"


def _to_event(
    code: str,
    source: str,
    published_at: datetime,
    title: str,
    url: str,
    *,
    source_category: str = "",
    has_xbrl: bool | None = None,
    listing_exchange: str = "",
    has_update_history: bool | None = None,
) -> ScrapedEvent:
    event_type = _classify_event_type(title)
    event_scope, issuer_specificity = _classify_scope(source, title)
    novelty = _classify_novelty(title)
    polarity = _classify_polarity(title)
    originality = "primary" if source == "tdnet" else "recap"
    confidence = 0.9 if source == "tdnet" else 0.7
    return ScrapedEvent(
        code=code,
        source=source,
        published_at=published_at.isoformat(),
        title=title.strip(),
        raw_text_short=title.strip(),
        event_type=event_type,
        event_polarity=polarity,
        issuer_specificity=issuer_specificity,
        novelty_level=novelty,
        expected_impact_horizon="short",
        confidence_base=confidence,
        event_scope=event_scope,
        originality=originality,
        url=url,
        source_category=source_category,
        has_xbrl=has_xbrl,
        listing_exchange=listing_exchange,
        has_update_history=has_update_history,
    )


def fetch_kabutan_news_for_month(
    code: str,
    *,
    yyyymm00: str | None = None,
    nmode: int = 0,
    timeout: int | None = None,
    session: requests.Session | None = None,
) -> list[ScrapedEvent]:
    timeout_sec = timeout if timeout is not None else get_http_timeout()
    s = session or requests.Session()
    if not session:
        s.headers.update(_DEFAULT_HEADERS)
    params: dict[str, str | int] = {"code": code, "nmode": nmode}
    if yyyymm00:
        params["date"] = yyyymm00
    url = f"{_KABUTAN_BASE}/stock/news"
    resp = s.get(url, params=params, timeout=timeout_sec)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[ScrapedEvent] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        dt = _parse_kabutan_dt(tds[0].get_text(" ", strip=True))
        if dt is None:
            continue
        source_category = ""
        if len(tds) >= 3:
            source_category = tds[1].get_text(" ", strip=True)
            a = tds[2].find("a", href=True)
        else:
            a = tr.find("a", href=True)
        if a is None:
            continue
        href = a["href"]
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        if href.startswith("/"):
            href = f"{_KABUTAN_BASE}{href}"
        events.append(
            _to_event(
                code=str(code),
                source="kabutan",
                published_at=dt,
                title=title,
                url=href,
                source_category=source_category,
            )
        )
    return events


def fetch_tdnet_disclosures_for_date(
    target_day: date,
    *,
    max_pages: int = 5,
    timeout: int | None = None,
    session: requests.Session | None = None,
) -> list[ScrapedEvent]:
    timeout_sec = timeout if timeout is not None else get_http_timeout()
    s = session or requests.Session()
    if not session:
        s.headers.update(_DEFAULT_HEADERS)
    events: list[ScrapedEvent] = []
    ymd = target_day.strftime("%Y%m%d")
    for page in range(1, max_pages + 1):
        page_str = f"{page:03d}"
        url = f"{_TDNET_BASE}/I_list_{page_str}_{ymd}.html"
        resp = s.get(url, timeout=timeout_sec)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        soup = BeautifulSoup(resp.text, "html.parser")
        page_events = 0
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            hhmm = tds[0].get_text(" ", strip=True)
            code_raw = tds[1].get_text(" ", strip=True).upper()
            if not _RE_CODE.match(code_raw):
                continue
            dt = _parse_tdnet_dt(target_day, hhmm)
            if dt is None:
                continue
            a = tds[3].find("a", href=True)
            if a is None:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = f"https://www.release.tdnet.info{href}"
            elif not href.startswith("http"):
                href = f"{_TDNET_BASE}/{href.lstrip('./')}"
            code = _norm_tdnet_code(code_raw)
            has_xbrl = bool(tds[4].get_text(" ", strip=True)) if len(tds) >= 5 else None
            listing_exchange = tds[5].get_text(" ", strip=True) if len(tds) >= 6 else ""
            has_update_history = bool(tds[6].get_text(" ", strip=True)) if len(tds) >= 7 else None
            events.append(
                _to_event(
                    code=code,
                    source="tdnet",
                    published_at=dt,
                    title=title,
                    url=href,
                    has_xbrl=has_xbrl,
                    listing_exchange=listing_exchange,
                    has_update_history=has_update_history,
                )
            )
            page_events += 1
        if page_events == 0:
            break
    return events


def filter_events_by_window(events: Iterable[ScrapedEvent], start_date: date, end_date: date) -> list[ScrapedEvent]:
    out: list[ScrapedEvent] = []
    for e in events:
        try:
            d = datetime.fromisoformat(e.published_at).date()
        except ValueError:
            continue
        if start_date <= d <= end_date:
            out.append(e)
    return out
