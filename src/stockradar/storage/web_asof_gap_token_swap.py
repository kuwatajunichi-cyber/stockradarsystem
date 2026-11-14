"""Rewrite stored GAP_UP / GAP_DOWN tokens in committed web-asof bundles.

Historical candle_labels used the pre-9.4 mapping. The screen dictionary now
matches compute_price_text, so those tokens must be swapped before the as-of
is shown. Numeric series are left untouched.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from stockradar.storage.web_asof_bundle import validate_web_asof_bundle

GAP_UP = "GAP_UP"
GAP_DOWN = "GAP_DOWN"
PRICE_UP = "上窓＋"
PRICE_DOWN = "下窓＋"
_PRICE_UP_TMP = "\u0000GAP_JA_UP\u0000"
_PRICE_DOWN_TMP = "\u0000GAP_JA_DOWN\u0000"

# Main merge of the generator mapping fix (PR 184, 62c5e702).
GENERATOR_FIX_COMMITTED_AT_UTC = datetime(2026, 11, 14, 6, 11, 49, tzinfo=timezone.utc)
SWAP_WORKFLOW = "web_asof_gap_token_swap"
SWAP_MODE = "replay"
SWAP_REPOSITORY = "kuwatajunichi-cyber/stockradarsystem"


class GapTokenSwapError(ValueError):
    """A row cannot be rewritten without losing meaning."""


@dataclass(frozen=True)
class GapSwapStats:
    rows: int
    rows_with_gap_token: int
    rows_with_gap_phrase: int
    labels_changed: int
    price_text_changed: int


@dataclass(frozen=True)
class BundlePointer:
    trade_date: str
    benchmark: str
    object_key: str
    committed_at_utc: str


def parse_committed_at(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def swap_github_run_id(as_of: str) -> int:
    return int(as_of.replace("-", ""))


def label_tokens(labels: str) -> list[str]:
    return [token.strip() for token in str(labels).split(",") if token.strip()]


def swap_gap_label_tokens(labels: str) -> str:
    tokens = label_tokens(labels)
    has_up = GAP_UP in tokens
    has_down = GAP_DOWN in tokens
    if has_up and has_down:
        raise GapTokenSwapError("row has both GAP_UP and GAP_DOWN")
    swapped: list[str] = []
    for token in tokens:
        if token == GAP_UP:
            swapped.append(GAP_DOWN)
        elif token == GAP_DOWN:
            swapped.append(GAP_UP)
        else:
            swapped.append(token)
    return ",".join(swapped)


def swap_gap_price_text(text: str) -> str:
    if PRICE_UP not in text and PRICE_DOWN not in text:
        return text
    return (
        text.replace(PRICE_UP, _PRICE_UP_TMP)
        .replace(PRICE_DOWN, _PRICE_DOWN_TMP)
        .replace(_PRICE_UP_TMP, PRICE_DOWN)
        .replace(_PRICE_DOWN_TMP, PRICE_UP)
    )


def sakata_gap_token(
    *,
    prev_high: float,
    prev_low: float,
    today_high: float,
    today_low: float,
) -> str | None:
    if prev_high < today_low:
        return GAP_UP
    if prev_low > today_high:
        return GAP_DOWN
    return None


def series_canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload.get("series"), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _swap_row(row: Mapping[str, Any], *, as_of: str) -> tuple[dict[str, Any], bool, bool]:
    out = dict(row)
    labels_changed = False
    phrase_changed = False
    raw_labels = out.get("candle_labels")
    if raw_labels is not None and str(raw_labels).strip():
        tokens = label_tokens(str(raw_labels))
        if GAP_UP in tokens or GAP_DOWN in tokens:
            try:
                swapped = swap_gap_label_tokens(str(raw_labels))
            except GapTokenSwapError as exc:
                code = str(out.get("code") or "")
                raise GapTokenSwapError(f"{as_of} {code}: {exc}") from exc
            if swapped != str(raw_labels):
                out["candle_labels"] = swapped
                labels_changed = True
    raw_text = out.get("price_text")
    if raw_text is not None:
        swapped_text = swap_gap_price_text(str(raw_text))
        if swapped_text != str(raw_text):
            out["price_text"] = swapped_text
            phrase_changed = True
    return out, labels_changed, phrase_changed


def swap_gap_bundle(payload: Mapping[str, Any]) -> tuple[dict[str, Any], GapSwapStats]:
    """Return a new payload with gap tokens swapped. ``series`` is the same object."""
    rows_in = payload.get("rows")
    if not isinstance(rows_in, list):
        raise GapTokenSwapError("rows must be an array")
    as_of = str(payload.get("as_of") or "")
    rows_out: list[dict[str, Any]] = []
    token_rows = 0
    phrase_rows = 0
    labels_changed = 0
    phrases_changed = 0
    for row in rows_in:
        if not isinstance(row, dict):
            raise GapTokenSwapError("each row must be an object")
        tokens = label_tokens(str(row.get("candle_labels") or ""))
        if GAP_UP in tokens or GAP_DOWN in tokens:
            token_rows += 1
        text = str(row.get("price_text") or "")
        if PRICE_UP in text or PRICE_DOWN in text:
            phrase_rows += 1
        swapped, did_labels, did_phrase = _swap_row(row, as_of=as_of)
        if did_labels:
            labels_changed += 1
        if did_phrase:
            phrases_changed += 1
        rows_out.append(swapped)
    out = dict(payload)
    out["rows"] = rows_out
    out["series"] = payload["series"]
    validate_web_asof_bundle(out)
    if series_canonical_bytes(out) != series_canonical_bytes(payload):
        raise GapTokenSwapError(f"{as_of}: series changed")
    if [row.get("code") for row in rows_out] != [row.get("code") for row in rows_in]:
        raise GapTokenSwapError(f"{as_of}: row codes changed")
    stats = GapSwapStats(
        rows=len(rows_out),
        rows_with_gap_token=token_rows,
        rows_with_gap_phrase=phrase_rows,
        labels_changed=labels_changed,
        price_text_changed=phrases_changed,
    )
    return out, stats


def latest_pre_cutoff_pointers(
    rows: Sequence[Mapping[str, Any]],
    *,
    cutoff: datetime = GENERATOR_FIX_COMMITTED_AT_UTC,
) -> dict[tuple[str, str], BundlePointer]:
    """Keep the latest committed pointer per (as-of, bench) if it is before cutoff."""
    latest: dict[tuple[str, str], BundlePointer] = {}
    latest_at: dict[tuple[str, str], datetime] = {}
    for row in rows:
        trade_date = str(row.get("trade_date") or "").strip()
        benchmark = str(row.get("benchmark") or "").strip().lower()
        object_key = str(row.get("object_key") or "").strip()
        committed_at = str(row.get("committed_at_utc") or "").strip()
        if not trade_date or benchmark not in {"topix", "nikkei"} or not object_key:
            continue
        if not committed_at:
            continue
        at = parse_committed_at(committed_at)
        key = (trade_date, benchmark)
        prev = latest_at.get(key)
        if prev is None or at > prev:
            latest_at[key] = at
            latest[key] = BundlePointer(
                trade_date=trade_date,
                benchmark=benchmark,
                object_key=object_key,
                committed_at_utc=committed_at,
            )
    return {key: pointer for key, pointer in latest.items() if latest_at[key] < cutoff}


def pair_as_of_pointers(
    pointers: Mapping[tuple[str, str], BundlePointer],
) -> tuple[list[tuple[str, BundlePointer, BundlePointer]], list[str]]:
    """Group topix+nikkei. Dates missing a bench are listed separately."""
    dates = sorted({trade_date for trade_date, _bench in pointers})
    pairs: list[tuple[str, BundlePointer, BundlePointer]] = []
    missing: list[str] = []
    for as_of in dates:
        topix = pointers.get((as_of, "topix"))
        nikkei = pointers.get((as_of, "nikkei"))
        if topix is None or nikkei is None:
            missing.append(as_of)
            continue
        pairs.append((as_of, topix, nikkei))
    return pairs, missing
