"""Pure helpers for ADR-005 Monthly new-Core backfill (request identity / core delta)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence

_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_RELEASE_MONTH = re.compile(r"^\d{4}-\d{2}$")


def canonical_json_sha256_v1(payload: Any) -> str:
    """NFC on input strings only, then compact sorted JSON (ADR-005 §7)."""

    def _normalize(value: Any) -> Any:
        if isinstance(value, str):
            return unicodedata.normalize("NFC", value)
        if isinstance(value, dict):
            return {str(k): _normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_normalize(v) for v in value]
        return value

    normalized = _normalize(payload)
    body = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(body.encode("utf-8")).hexdigest()


def current_core_logical_digest(codes: Iterable[str]) -> str:
    cleaned = sorted({str(c).strip() for c in codes if str(c).strip()})
    return canonical_json_sha256_v1(cleaned)


def core_delta(*, previous_codes: Iterable[str], current_codes: Iterable[str]) -> list[str]:
    prev = {str(c).strip() for c in previous_codes if str(c).strip()}
    cur = {str(c).strip() for c in current_codes if str(c).strip()}
    return sorted(cur - prev)


@dataclass(frozen=True)
class CommittedMonthlySnapshotRow:
    """Committed monthly_snapshots row fields needed for canonical selection."""

    monthly_tag: str
    snapshot_date: str  # YYYY-MM-DD
    github_run_id: int
    object_keys: Mapping[str, Any]

    @property
    def release_month(self) -> str:
        return str(self.snapshot_date).strip()[:7]


def canonical_release_for_month(
    release_month: str,
    committed_rows: Sequence[CommittedMonthlySnapshotRow],
) -> CommittedMonthlySnapshotRow | None:
    """Last-wins canonical winner for a calendar month. No fallback_latest."""
    month = str(release_month).strip()
    if not _RELEASE_MONTH.match(month):
        raise ValueError(f"invalid release_month: {release_month!r}")
    eligible = [row for row in committed_rows if row.release_month == month]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda row: (date.fromisoformat(str(row.snapshot_date).strip()), int(row.github_run_id)),
    )


def previous_month_key(release_month: str) -> str:
    month = str(release_month).strip()
    if not _RELEASE_MONTH.match(month):
        raise ValueError(f"invalid release_month: {release_month!r}")
    y, m = int(month[:4]), int(month[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def previous_core_row_for_release_month(
    release_month: str,
    committed_rows: Sequence[CommittedMonthlySnapshotRow],
) -> CommittedMonthlySnapshotRow | None:
    """Latest committed Core in the calendar month immediately before release_month."""
    prev = previous_month_key(release_month)
    return canonical_release_for_month(prev, committed_rows)


def build_request_id_v1(
    *,
    release_month: str,
    previous_monthly_tag: str,
    current_core_logical_digest_hex: str,
    metric_set_version_id: str,
    added_codes: Sequence[str],
    partition_index: int = 0,
    partition_count: int = 1,
    partition_codes: Sequence[str] | None = None,
) -> str:
    digest = str(current_core_logical_digest_hex).strip().lower()
    if not _HEX64.match(digest):
        raise ValueError("current_core_logical_digest must be 64 hex chars")
    if partition_index < 0 or partition_count < 1 or partition_index >= partition_count:
        raise ValueError("invalid partition_index/partition_count")
    codes = list(added_codes) if partition_codes is None else list(partition_codes)
    cleaned = sorted({str(c).strip() for c in codes if str(c).strip()})
    added_digest = canonical_json_sha256_v1(cleaned)
    payload = {
        "schema_version": 1,
        "release_month": str(release_month).strip(),
        "previous_monthly_tag": str(previous_monthly_tag).strip(),
        "current_core_logical_digest": digest,
        "metric_set_version_id": str(metric_set_version_id).strip().lower(),
        "added_codes_digest": added_digest,
        "partition_index": int(partition_index),
        "partition_count": int(partition_count),
        "partition_codes_digest": added_digest,
    }
    return "mnc-v1-" + canonical_json_sha256_v1(payload)


def core_object_key_from_row(row: CommittedMonthlySnapshotRow) -> str | None:
    core = row.object_keys.get("core") if isinstance(row.object_keys, Mapping) else None
    if isinstance(core, Mapping):
        key = core.get("object_key")
        return str(key) if key else None
    if isinstance(core, str) and core.strip():
        return core.strip()
    return None

@dataclass(frozen=True)
class MonthlyBackfillDecision:
    outcome: str  # runnable | noop | blocked | grandfather
    reason_code: str | None
    added_codes: tuple[str, ...]
    previous_monthly_tag: str | None


def codes_from_core_csv_bytes(content: bytes) -> list[str]:
    """Parse equity_domestic_core_with_name.csv bytes; code column required."""
    import csv
    import io

    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "code" not in reader.fieldnames:
        raise ValueError("core csv missing code column")
    codes: list[str] = []
    for row in reader:
        code = str(row.get("code") or "").strip()
        if code:
            codes.append(code)
    return codes


def decide_monthly_backfill_outcome(
    *,
    release_month: str,
    feature_start_release_month: str | None,
    previous_row: CommittedMonthlySnapshotRow | None,
    current_codes: Sequence[str],
    previous_codes: Sequence[str] | None,
    expected_trade_dates: Sequence[str],
    max_added_codes: int = 50,
    max_work_units: int = 4000,
) -> MonthlyBackfillDecision:
    """Pure outcome for Monthly winner commit (ADR-005 §1 / §4)."""
    month = str(release_month).strip()
    if not _RELEASE_MONTH.match(month):
        raise ValueError(f"invalid release_month: {release_month!r}")
    fs = (
        str(feature_start_release_month).strip()
        if feature_start_release_month is not None and str(feature_start_release_month).strip()
        else None
    )
    if fs is not None and not _RELEASE_MONTH.match(fs):
        raise ValueError(f"invalid feature_start_release_month: {feature_start_release_month!r}")
    if fs is None:
        # Pre-enable: caller must commit snapshot without request.
        raise ValueError("feature_start_unset")
    if month < fs:
        return MonthlyBackfillDecision(
            outcome="grandfather",
            reason_code="before_feature_start",
            added_codes=(),
            previous_monthly_tag=previous_row.monthly_tag if previous_row else None,
        )
    if previous_row is None or previous_codes is None:
        return MonthlyBackfillDecision(
            outcome="blocked",
            reason_code="missing_previous_core",
            added_codes=(),
            previous_monthly_tag=None,
        )
    added = tuple(core_delta(previous_codes=previous_codes, current_codes=current_codes))
    if not added:
        return MonthlyBackfillDecision(
            outcome="noop",
            reason_code=None,
            added_codes=(),
            previous_monthly_tag=previous_row.monthly_tag,
        )
    if len(added) > int(max_added_codes):
        return MonthlyBackfillDecision(
            outcome="blocked",
            reason_code="added_codes_over_limit",
            added_codes=added,
            previous_monthly_tag=previous_row.monthly_tag,
        )
    dates = list(expected_trade_dates)
    if not dates:
        return MonthlyBackfillDecision(
            outcome="blocked",
            reason_code="coverage_empty",
            added_codes=added,
            previous_monthly_tag=previous_row.monthly_tag,
        )
    work = len(added) * len(dates)
    if work > int(max_work_units):
        return MonthlyBackfillDecision(
            outcome="blocked",
            reason_code="work_units_over_limit",
            added_codes=added,
            previous_monthly_tag=previous_row.monthly_tag,
        )
    return MonthlyBackfillDecision(
        outcome="runnable",
        reason_code=None,
        added_codes=added,
        previous_monthly_tag=previous_row.monthly_tag,
    )


def expected_trade_dates_from_committed_snapshots(trade_dates: Sequence[str]) -> list[str]:
    """Ascending unique YYYY-MM-DD list for request expected_trade_dates (ADR-005)."""
    cleaned = sorted({str(d).strip() for d in trade_dates if str(d).strip()})
    for d in cleaned:
        date.fromisoformat(d)
    return cleaned
