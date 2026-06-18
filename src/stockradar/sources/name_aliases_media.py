from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from stockradar.event_causes.name_alias_rules import (
    is_valid_alias,
    normalize_alias,
    normalize_code,
    strip_tdnet_market_prefix,
)


@dataclass
class MediaStats:
    requests: int = 0
    success: int = 0
    fail: int = 0
    retry: int = 0
    latency_ms_total: int = 0

    def as_dict(self) -> dict[str, float | int]:
        avg = 0.0 if self.requests == 0 else self.latency_ms_total / float(self.requests)
        return {
            "requests": self.requests,
            "success": self.success,
            "fail": self.fail,
            "retry": self.retry,
            "avg_latency_ms": round(avg, 2),
        }


@dataclass
class FetchPolicy:
    sleep_ms: int = 800
    sleep_jitter_ms: int = 400
    retry_max: int = 3
    retry_backoff_ms: list[int] | None = None
    per_host_qps: float | None = None

    def __post_init__(self) -> None:
        if self.retry_backoff_ms is None:
            self.retry_backoff_ms = [1000, 3000, 7000]


def _default_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }


def _sleep_with_policy(
    policy: FetchPolicy,
    *,
    host: str,
    host_next_ts: dict[str, float],
    rng: Any | None,
) -> None:
    now = time.time()
    if policy.per_host_qps and policy.per_host_qps > 0:
        min_interval = 1.0 / policy.per_host_qps
        next_ts = host_next_ts.get(host, 0.0)
        if now < next_ts:
            time.sleep(next_ts - now)
        host_next_ts[host] = max(now, next_ts) + min_interval
    jitter = 0
    if policy.sleep_jitter_ms > 0:
        if rng is not None:
            jitter = int(rng.randint(0, policy.sleep_jitter_ms))
        else:
            jitter = policy.sleep_jitter_ms // 2
    sleep_sec = (policy.sleep_ms + jitter) / 1000.0
    if sleep_sec > 0:
        time.sleep(sleep_sec)


def _request_text(
    *,
    url: str,
    session: requests.Session,
    policy: FetchPolicy,
    stats: MediaStats,
    host_next_ts: dict[str, float],
    rng: Any | None,
    params: dict[str, str] | None = None,
    count_404_as_fail: bool = True,
) -> str | None:
    host = urlparse(url).netloc
    for attempt in range(policy.retry_max):
        _sleep_with_policy(policy, host=host, host_next_ts=host_next_ts, rng=rng)
        t0 = time.time()
        stats.requests += 1
        try:
            resp = session.get(url, params=params, timeout=15)
            latency_ms = int((time.time() - t0) * 1000)
            stats.latency_ms_total += max(latency_ms, 0)
            if resp.status_code == 200:
                stats.success += 1
                resp.encoding = resp.apparent_encoding or resp.encoding
                return resp.text
            if resp.status_code == 404:
                if count_404_as_fail:
                    stats.fail += 1
                return None
            if attempt + 1 < policy.retry_max:
                stats.retry += 1
                backoff = policy.retry_backoff_ms[min(attempt, len(policy.retry_backoff_ms) - 1)]
                time.sleep(backoff / 1000.0)
            else:
                stats.fail += 1
                return None
        except Exception:
            latency_ms = int((time.time() - t0) * 1000)
            stats.latency_ms_total += max(latency_ms, 0)
            if attempt + 1 < policy.retry_max:
                stats.retry += 1
                backoff = policy.retry_backoff_ms[min(attempt, len(policy.retry_backoff_ms) - 1)]
                time.sleep(backoff / 1000.0)
                continue
            stats.fail += 1
            return None
    return None


def _extract_kabutan_title_aliases(title: str, code: str) -> list[str]:
    m = re.match(rf"^(?P<head>.+?)【{re.escape(code)}】", title)
    if not m:
        m = re.match(r"^(?P<head>.+?)【[0-9A-Z]{4,5}】", title)
    if not m:
        return []
    head = normalize_alias(m.group("head"))
    pm = re.match(r"^(?P<base>.+?)[（(](?P<alias>.+?)[）)]$", head)
    vals = [head] if not pm else [pm.group("base"), pm.group("alias")]
    out: list[str] = []
    for v in vals:
        s = normalize_alias(v)
        if is_valid_alias(s) and s not in out:
            out.append(s)
    return out


def fetch_kabutan_aliases_for_code(
    code: str,
    *,
    session: requests.Session | None = None,
    policy: FetchPolicy | None = None,
    stats: MediaStats | None = None,
    host_next_ts: dict[str, float] | None = None,
    rng: Any | None = None,
) -> list[str]:
    s = session or requests.Session()
    if not session:
        s.headers.update(_default_headers())
    pol = policy or FetchPolicy()
    st = stats or MediaStats()
    host_map = host_next_ts if host_next_ts is not None else {}
    url = f"https://kabutan.jp/stock/?code={code}"
    text = _request_text(url=url, session=s, policy=pol, stats=st, host_next_ts=host_map, rng=rng)
    if not text:
        return []
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return _extract_kabutan_title_aliases(title, code)


def fetch_nikkei_aliases_for_code(
    code: str,
    *,
    session: requests.Session | None = None,
    policy: FetchPolicy | None = None,
    stats: MediaStats | None = None,
    host_next_ts: dict[str, float] | None = None,
    rng: Any | None = None,
) -> list[str]:
    s = session or requests.Session()
    if not session:
        s.headers.update(_default_headers())
    pol = policy or FetchPolicy()
    st = stats or MediaStats()
    host_map = host_next_ts if host_next_ts is not None else {}
    url = f"https://www.nikkei.com/nkd/company/?scode={code}"
    text = _request_text(url=url, session=s, policy=pol, stats=st, host_next_ts=host_map, rng=rng)
    if not text:
        return []
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    vals = re.findall(r"【([^】]+)】", title)
    out: list[str] = []
    for v in vals:
        s_v = normalize_alias(v)
        if is_valid_alias(s_v) and s_v not in out:
            out.append(s_v)
    return out


def fetch_reuters_aliases_for_code(
    code: str,
    *,
    session: requests.Session | None = None,
    policy: FetchPolicy | None = None,
    stats: MediaStats | None = None,
    host_next_ts: dict[str, float] | None = None,
    rng: Any | None = None,
) -> list[str]:
    """Reuters 別称取得は jp.reuters.com の応答不安定のため無効化。"""
    _ = (code, session, policy, stats, host_next_ts, rng)
    return []


def fetch_tdnet_issuer_counts(
    *,
    codes: set[str],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
    policy: FetchPolicy | None = None,
    stats: MediaStats | None = None,
    host_next_ts: dict[str, float] | None = None,
    rng: Any | None = None,
    max_pages: int = 7,
) -> dict[str, dict[str, int]]:
    s = session or requests.Session()
    if not session:
        s.headers.update(_default_headers())
    pol = policy or FetchPolicy()
    st = stats or MediaStats()
    host_map = host_next_ts if host_next_ts is not None else {}
    out: dict[str, dict[str, int]] = {}
    total_days = (end_date - start_date).days + 1
    for i in range(max(total_days, 0)):
        d = start_date + timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        for page in range(1, max_pages + 1):
            url = f"https://www.release.tdnet.info/inbs/I_list_{page:03d}_{ymd}.html"
            text = _request_text(
                url=url,
                session=s,
                policy=pol,
                stats=st,
                host_next_ts=host_map,
                rng=rng,
                count_404_as_fail=False,
            )
            if not text:
                break
            soup = BeautifulSoup(text, "html.parser")
            page_rows = 0
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                c = normalize_code(tds[1].get_text(" ", strip=True))
                if not c or c not in codes:
                    continue
                issuer = normalize_alias(tds[2].get_text(" ", strip=True))
                issuer = strip_tdnet_market_prefix(issuer)
                if not is_valid_alias(issuer):
                    continue
                out.setdefault(c, {})
                out[c][issuer] = out[c].get(issuer, 0) + 1
                page_rows += 1
            if page_rows == 0:
                break
    return out

