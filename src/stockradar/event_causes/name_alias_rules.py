from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

_RE_CODE = re.compile(r"^[0-9A-Z]{4,5}$")
_RE_SPACES = re.compile(r"\s+")
_RE_SHORT_ASCII = re.compile(r"^[A-Za-z]{1,2}$")
_RE_DROP_FOR_DEDUP = re.compile(r"[\s・･\-‐－_／/&＆,，.。]+")

_NOISE_WORDS = (
    "最新ニュース",
    "ニュース",
    "株価",
    "reuters",
    "stock price",
    "latest news",
    "quote",
    "提出会社",
    "上場会社",
    "日本経済新聞",
    "日経",
)


@dataclass(frozen=True)
class AliasThresholds:
    added_aliases_max: int = 400
    media_success_rate_min: float = 0.85
    low_ratio_max: float = 0.35


def normalize_code(code: str) -> str | None:
    c = str(code or "").strip().upper()
    if not c:
        return None
    if not _RE_CODE.match(c):
        return None
    # TDnet uses 5-digit code with trailing zero (e.g. 72030)
    if len(c) == 5 and c.endswith("0"):
        c = c[:-1]
    if len(c) not in (4, 5):
        return None
    return c


def normalize_alias(alias: str) -> str:
    s = html.unescape(str(alias or ""))
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = _RE_SPACES.sub(" ", s)
    return s


def dedup_key(alias: str) -> str:
    s = normalize_alias(alias).lower()
    s = _RE_DROP_FOR_DEDUP.sub("", s)
    return s


def strip_tdnet_market_prefix(alias: str) -> str:
    s = normalize_alias(alias)
    s = re.sub(r"^(?:[ＧG]-\s*)", "", s)
    s = re.sub(r"^(?:東証|名証|札証|福証)[A-Z0-9０-９]*\s*", "", s)
    s = re.sub(r"^(?:TOKYO\s+PRO\s+Market)\s*", "", s, flags=re.I)
    return s.strip()


def is_noise_alias(alias: str) -> bool:
    s = normalize_alias(alias)
    if not s:
        return True
    low = s.lower()
    return any(w in low for w in _NOISE_WORDS)


def is_valid_alias(alias: str) -> bool:
    s = normalize_alias(alias)
    if not s:
        return False
    if len(dedup_key(s)) <= 1:
        return False
    if len(s) > 80:
        return False
    if _RE_SHORT_ASCII.match(s):
        return False
    if is_noise_alias(s):
        return False
    return True


def classify_confidence(*, sources: set[str], alias: str, exists_in_base: bool) -> str:
    if exists_in_base:
        return "high"
    if len(sources) >= 2:
        return "high"
    if not is_valid_alias(alias):
        return "low"
    # Single-source short ASCII aliases are more collision-prone.
    if re.fullmatch(r"[A-Za-z]{3,5}", normalize_alias(alias)):
        return "low"
    return "medium"


def evaluate_anomalies(
    *,
    added_aliases: int,
    media_success_rate: float,
    low_ratio: float,
    thresholds: AliasThresholds,
    enforce_media_success_rate: bool = True,
) -> list[str]:
    problems: list[str] = []
    if added_aliases > thresholds.added_aliases_max:
        problems.append(
            f"added_aliases_exceeded: {added_aliases} > {thresholds.added_aliases_max}"
        )
    if enforce_media_success_rate and media_success_rate < thresholds.media_success_rate_min:
        problems.append(
            "media_success_rate_too_low: "
            f"{media_success_rate:.4f} < {thresholds.media_success_rate_min:.4f}"
        )
    if low_ratio > thresholds.low_ratio_max:
        problems.append(f"low_ratio_too_high: {low_ratio:.4f} > {thresholds.low_ratio_max:.4f}")
    return problems

