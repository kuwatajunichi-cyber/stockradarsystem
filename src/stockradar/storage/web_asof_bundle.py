"""Pure contract for Track D as-of view bundles (derived-web-asof)."""
from __future__ import annotations

import gzip
import hashlib
import json
from typing import Any, Mapping

SCHEMA_ID = "web_asof_bundle_v1"
AXIS_LEN = 60
BENCHMARKS = frozenset({"topix", "nikkei"})
GZIP_MAX_BYTES = 8 * 1024 * 1024
SMA75_LOOKBACK_TRADING_DAYS = 105
SMA75_NON_NULL_RATE_MIN = 0.98
BUNDLE_FAILURE_FAILS_DAILY = True

OBJECT_KEY_TEMPLATE = (
    "derived-web-asof/metric-set={metric_set_version_id}/"
    "benchmark={benchmark}/as-of={as_of}/bundle.json.gz"
)

ROW_METRIC_KEYS: tuple[str, ...] = (
    "z_turnover_60",
    "rs_acceleration",
    "rs_acceleration_zscore",
    "rs31",
    "rs63",
    "rs126",
    "rs252",
    "rs_sma75",
)

# Last-bar only (D-9 column panel). Not part of the 60-session series.
OPTIONAL_LAST_BAR_KEYS: tuple[str, ...] = (
    "turnover_ma_ratio_60",
    "price_change_pct",
    "perfect_order_days",
    "beta_adjusted_rs",
    "information_ratio",
)

SERIES_METRIC_KEYS: tuple[str, ...] = ROW_METRIC_KEYS

ROW_IDENTITY_KEYS: tuple[str, ...] = (
    "code",
    "name",
    "price_text",
    "event_news_bundle",
    "research_prompt_block",
    "candle_labels",
    "link_kabutan",
    "link_kabutan_chart",
    "link_kabutan_news",
    "link_buffett",
    "link_minkabu",
    "link_yahoo",
)

REQUIRED_TOP_KEYS: tuple[str, ...] = (
    "schema_id",
    "as_of",
    "benchmark",
    "metric_set_version_id",
    "set_fingerprint",
    "axis_dates",
    "rows",
    "series",
)


class WebAsofBundleError(ValueError):
    """Bundle failed the first-live JSON contract."""


def object_key(*, metric_set_version_id: str, benchmark: str, as_of: str) -> str:
    bench = benchmark.strip().lower()
    if bench not in BENCHMARKS:
        raise WebAsofBundleError(f"benchmark must be topix or nikkei, got {benchmark!r}")
    return OBJECT_KEY_TEMPLATE.format(
        metric_set_version_id=metric_set_version_id.strip().lower(),
        benchmark=bench,
        as_of=as_of.strip(),
    )


def physical_bundle_object_key(
    *,
    metric_set_version_id: str,
    benchmark: str,
    as_of: str,
    generation_id: str,
    digest: str,
) -> str:
    prefix = object_key(
        metric_set_version_id=metric_set_version_id,
        benchmark=benchmark,
        as_of=as_of,
    )
    if not prefix.endswith("/bundle.json.gz"):
        raise WebAsofBundleError(f"unexpected logical key: {prefix!r}")
    return (
        prefix[: -len("bundle.json.gz")]
        + f"generation={generation_id.strip().lower()}/bundle-sha256={digest.strip().lower()}.json.gz"
    )


def physical_manifest_object_key(
    *,
    metric_set_version_id: str,
    as_of: str,
    generation_id: str,
    digest: str,
) -> str:
    uid = metric_set_version_id.strip().lower()
    return (
        f"derived-web-asof/metric-set={uid}/as-of={as_of.strip()}/"
        f"generation={generation_id.strip().lower()}/manifest-sha256={digest.strip().lower()}.json"
    )


def gzip_bundle_bytes(payload: Mapping[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, mtime=0, compresslevel=9)


def gunzip_bundle_bytes(blob: bytes) -> dict[str, Any]:
    if len(blob) >= GZIP_MAX_BYTES:
        raise WebAsofBundleError(
            f"gzip object must be smaller than {GZIP_MAX_BYTES} bytes, got {len(blob)}"
        )
    raw = gzip.decompress(blob)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise WebAsofBundleError("bundle JSON must be an object")
    return data


def sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    parts = value.split("-")
    if len(parts) != 3:
        return False
    y, m, d = parts
    return y.isdigit() and m.isdigit() and d.isdigit() and len(y) == 4


def _is_null_or_number(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_web_asof_bundle(payload: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED_TOP_KEYS if k not in payload]
    if missing:
        raise WebAsofBundleError(f"missing top-level keys: {missing}")
    if payload.get("schema_id") != SCHEMA_ID:
        raise WebAsofBundleError(f"schema_id must be {SCHEMA_ID!r}")
    as_of = payload.get("as_of")
    if not _is_iso_date(as_of):
        raise WebAsofBundleError("as_of must be YYYY-MM-DD")
    bench = str(payload.get("benchmark") or "").strip().lower()
    if bench not in BENCHMARKS:
        raise WebAsofBundleError("benchmark must be topix or nikkei")
    set_id = payload.get("metric_set_version_id")
    if not isinstance(set_id, str) or not set_id.strip():
        raise WebAsofBundleError("metric_set_version_id required")
    fingerprint = payload.get("set_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise WebAsofBundleError("set_fingerprint must be 64 hex chars")
    axis = payload.get("axis_dates")
    if not isinstance(axis, list) or len(axis) != AXIS_LEN:
        raise WebAsofBundleError(f"axis_dates must have length {AXIS_LEN}")
    if any(not _is_iso_date(d) for d in axis):
        raise WebAsofBundleError("axis_dates must be YYYY-MM-DD")
    if axis[-1] != as_of:
        raise WebAsofBundleError("axis_dates last element must equal as_of")
    rows = payload.get("rows")
    series = payload.get("series")
    if not isinstance(rows, list):
        raise WebAsofBundleError("rows must be an array")
    if not isinstance(series, dict):
        raise WebAsofBundleError("series must be an object keyed by code")
    codes: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise WebAsofBundleError("each row must be an object")
        code = row.get("code")
        if not isinstance(code, str) or len(code) != 4 or not all(
            ch.isdigit() or ("A" <= ch <= "Z") for ch in code
        ):
            raise WebAsofBundleError("row.code must be a 4-character JPX ticker")
        codes.append(code)
        if not isinstance(row.get("name"), str):
            raise WebAsofBundleError(f"row {code}: name must be a string")
        for key in ROW_METRIC_KEYS:
            if key not in row:
                raise WebAsofBundleError(f"row {code}: missing metric {key}")
            if not _is_null_or_number(row[key]):
                raise WebAsofBundleError(f"row {code}: {key} must be number or null")
        for key in OPTIONAL_LAST_BAR_KEYS:
            if key in row and not _is_null_or_number(row[key]):
                raise WebAsofBundleError(f"row {code}: {key} must be number or null")
        if "rs_sma75" not in row:
            raise WebAsofBundleError(f"row {code}: rs_sma75 column required")
    if len(codes) != len(set(codes)):
        raise WebAsofBundleError("row.code must be unique")
    if set(codes) != set(series):
        raise WebAsofBundleError("series keys must equal the set of row codes")
    for code in codes:
        series_row = series[code]
        if not isinstance(series_row, dict):
            raise WebAsofBundleError(f"series[{code}] must be an object")
        for key in SERIES_METRIC_KEYS:
            arr = series_row.get(key)
            if not isinstance(arr, list) or len(arr) != AXIS_LEN:
                raise WebAsofBundleError(
                    f"series[{code}].{key} must be length {AXIS_LEN}"
                )
            if any(not _is_null_or_number(v) for v in arr):
                raise WebAsofBundleError(
                    f"series[{code}].{key} values must be number or null"
                )
        last = {key: series_row[key][-1] for key in SERIES_METRIC_KEYS}
        row = next(r for r in rows if r["code"] == code)
        for key in SERIES_METRIC_KEYS:
            if last[key] != row.get(key):
                raise WebAsofBundleError(
                    f"row {code} {key} must equal series last bar"
                )


def sma75_non_null_rate(values: list[Any]) -> float:
    if not values:
        return 0.0
    present = sum(1 for v in values if v is not None)
    return present / len(values)


def sma75_cas_allowed(values: list[Any], *, min_rate: float = SMA75_NON_NULL_RATE_MIN) -> bool:
    if not values:
        return False
    return sma75_non_null_rate(values) >= min_rate
