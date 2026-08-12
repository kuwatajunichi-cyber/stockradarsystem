"""Canonical logical digest serialization (Phase 4.5 SSOT)."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from stockradar.metrics.normalize_instrument_code import normalize_instrument_code

SCHEMA_VERSION = 1

RowFlags = dict[str, Any]
TaggedAtom = dict[str, Any]
DigestRow = dict[str, Any]


def canonical_decimal_string(value: float) -> str:
    """Convert finite float to canonical decimal string (round-half-even, 10 dp)."""
    if not math.isfinite(value):
        raise ValueError(f"non-finite float cannot be canonicalized: {value!r}")
    dec = Decimal(str(value)).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_EVEN)
    if dec == 0:
        return "0"
    normalized = format(dec.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in ("-0", "-0.0"):
        return "0"
    return normalized


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def tagged_value_atom(*, metric_key: str, value_type: str, value: Any) -> TaggedAtom:
    atom: TaggedAtom = {"metric_key": metric_key, "type": value_type}
    if value_type == "float":
        if value is None:
            atom["value"] = None
        elif isinstance(value, float) and not math.isfinite(value):
            atom["value"] = None
        else:
            atom["value"] = canonical_decimal_string(float(value))
    elif value_type == "int":
        atom["value"] = None if value is None else int(value)
    elif value_type == "bool":
        atom["value"] = None if value is None else bool(value)
    elif value_type == "string":
        atom["value"] = None if value is None else _normalize_text(str(value))
    elif value_type == "null":
        atom["value"] = None
    else:
        raise ValueError(f"unsupported value_type: {value_type!r}")
    return atom


def row_flags_to_canonical(
    *,
    missing_metrics: list[str],
    non_finite_metrics: list[str],
    po_indeterminate: bool = False,
) -> RowFlags:
    return {
        "missing_metrics": list(missing_metrics),
        "non_finite_metrics": list(non_finite_metrics),
        "po_indeterminate": bool(po_indeterminate),
    }


def _serialize_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_logical_digest_payload(
    *,
    trade_date: str,
    metric_set_version_id: str,
    rows: list[DigestRow],
) -> dict[str, Any]:
    set_uuid = metric_set_version_id.strip().lower()
    sorted_rows = sorted(rows, key=lambda r: tuple(ord(c) for c in str(r["instrument_code"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date,
        "metric_set_version_id": set_uuid,
        "rows": sorted_rows,
    }


def compute_logical_digest(
    *,
    trade_date: str,
    metric_set_version_id: str,
    rows: list[DigestRow],
) -> tuple[str, bytes]:
    payload = build_logical_digest_payload(
        trade_date=trade_date,
        metric_set_version_id=metric_set_version_id,
        rows=rows,
    )
    raw = _serialize_payload(payload)
    digest = hashlib.sha256(raw).hexdigest()
    return digest, raw


def classify_metric_value(
    *,
    metric_key: str,
    value_type: str,
    raw_value: Any,
) -> tuple[Any, list[str], list[str]]:
    missing: list[str] = []
    non_finite: list[str] = []
    if raw_value is None:
        missing.append(metric_key)
        return None, missing, non_finite
    if value_type == "float":
        try:
            num = float(raw_value)
        except (TypeError, ValueError):
            missing.append(metric_key)
            return None, missing, non_finite
        if not math.isfinite(num):
            non_finite.append(metric_key)
            return None, missing, non_finite
        return num, missing, non_finite
    if value_type == "int":
        if raw_value is None:
            missing.append(metric_key)
            return None, missing, non_finite
        try:
            if isinstance(raw_value, float):
                if not math.isfinite(raw_value):
                    non_finite.append(metric_key)
                    return None, missing, non_finite
                if raw_value != int(raw_value):
                    missing.append(metric_key)
                    return None, missing, non_finite
                return int(raw_value), missing, non_finite
            return int(raw_value), missing, non_finite
        except (TypeError, ValueError):
            missing.append(metric_key)
            return None, missing, non_finite
    if value_type == "bool":
        return bool(raw_value), missing, non_finite
    if value_type == "string":
        return _normalize_text(str(raw_value)), missing, non_finite
    raise ValueError(f"unsupported value_type: {value_type!r}")


def build_digest_row(
    *,
    instrument_code: str,
    metric_keys_ordered: list[str],
    metric_types: dict[str, str],
    values_by_key: dict[str, Any],
    po_indeterminate: bool = False,
) -> DigestRow:
    missing: list[str] = []
    non_finite: list[str] = []
    atoms: list[TaggedAtom] = []
    for key in metric_keys_ordered:
        value_type = metric_types[key]
        normalized, miss, nf = classify_metric_value(
            metric_key=key,
            value_type=value_type,
            raw_value=values_by_key.get(key),
        )
        missing.extend(miss)
        non_finite.extend(nf)
        atoms.append(tagged_value_atom(metric_key=key, value_type=value_type, value=normalized))
    flags = row_flags_to_canonical(
        missing_metrics=sorted(set(missing), key=lambda k: metric_keys_ordered.index(k)),
        non_finite_metrics=sorted(set(non_finite), key=lambda k: metric_keys_ordered.index(k)),
        po_indeterminate=po_indeterminate,
    )
    return {
        "instrument_code": _normalize_text(normalize_instrument_code(instrument_code)),
        "values": atoms,
        "flags": flags,
    }
