"""Contract: Fake web-asof generation, CSV projection, lab SLO, shadow (no CAS)."""
from __future__ import annotations

import statistics
import time
from uuid import uuid4

import pytest

from stockradar.jobs.write_web_asof_bundle import (
    WebAsofGenerationRequest,
    build_web_asof_bundle_payload,
    encode_web_asof_bundle,
    project_csv_row,
    run_web_asof_generation,
    window_series_to_axis,
)
from stockradar.storage.derived_generation import (
    ArtifactProfile,
    BeginGenerationRequest,
    FakeMetricGenerationStore,
    SourceRunIdentity,
    WEB_ASOF_EXPECTED_OBJECT_COUNT,
)
from stockradar.storage.r2_object_store import FakeR2ObjectStore
from stockradar.storage.web_asof_bundle import (
    AXIS_LEN,
    GZIP_MAX_BYTES,
    SCHEMA_ID,
    gunzip_bundle_bytes,
)

pytestmark = pytest.mark.unit

_FP = "b" * 64
_SET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _axis() -> list[str]:
    days = [f"2026-07-{i:02d}" for i in range(1, 32)] + [f"2026-08-{i:02d}" for i in range(1, 32)]
    return days[:AXIS_LEN]


def _row(code: str = "7203", sma: float = 0.2) -> dict:
    return {
        "code": code,
        "name": "Toyota",
        "z_turnover_60": sma,
        "rs_acceleration": sma,
        "rs_acceleration_zscore": sma,
        "rs31": sma,
        "rs63": sma,
        "rs126": sma,
        "rs252": sma,
        "rs_sma75": sma,
    }


def _series_for(codes: list[str], axis: list[str], last: float = 0.2) -> dict:
    n = len(axis)
    body = {
        "z_turnover_60": [0.1] * (n - 1) + [last],
        "rs_acceleration": [0.1] * (n - 1) + [last],
        "rs_acceleration_zscore": [0.1] * (n - 1) + [last],
        "rs31": [0.1] * (n - 1) + [last],
        "rs63": [0.1] * (n - 1) + [last],
        "rs126": [0.1] * (n - 1) + [last],
        "rs252": [0.1] * (n - 1) + [last],
        "rs_sma75": [0.1] * (n - 1) + [last],
    }
    return {code: dict(body) for code in codes}


def _payload(bench: str, *, codes: list[str] | None = None, sma: float = 0.2) -> dict:
    axis = _axis()
    codes = codes or ["7203"]
    rows = [_row(code, sma=sma) for code in codes]
    return build_web_asof_bundle_payload(
        as_of=axis[-1],
        benchmark=bench,
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
        axis_dates=axis,
        rows=rows,
        series=_series_for(codes, axis, last=sma),
    )


def test_project_csv_row_unsuffixes_and_keeps_same_asof_news() -> None:
    as_of = "2026-08-31"
    csv_row = {
        "date": as_of,
        "code": "7203",
        "name": "Toyota",
        "z_turnover_60": 1.5,
        "rs31_topix": 0.11,
        "rs63_topix": 0.12,
        "rs126_topix": 0.13,
        "rs252_topix": 0.14,
        "rs_acceleration_topix": 0.01,
        "rs_acceleration_zscore_topix": 0.02,
        "rs_sma75_topix": 0.09,
        "turnover_ma_ratio_60": 2.5,
        "price_change_pct": -1.25,
        "perfect_order_days": 7,
        "beta_adjusted_rs_topix": 0.3,
        "information_ratio_topix": 0.4,
        "beta_adjusted_rs_nikkei": 0.5,
        "information_ratio_nikkei": 0.6,
        "event_news_1_title": "same-day news",
        "event_news_1_url": "https://example.invalid/news",
        "link_buffett": "https://example.invalid/7203",
    }
    row = project_csv_row(csv_row, bench="topix", as_of=as_of)
    assert row["rs31"] == pytest.approx(0.11)
    assert row["rs_sma75"] == pytest.approx(0.09)
    assert "rs31_topix" not in row
    assert row["turnover_ma_ratio_60"] == pytest.approx(2.5)
    assert row["price_change_pct"] == pytest.approx(-1.25)
    assert row["perfect_order_days"] == pytest.approx(7)
    assert row["beta_adjusted_rs"] == pytest.approx(0.3)
    assert row["information_ratio"] == pytest.approx(0.4)
    assert "beta_adjusted_rs_topix" not in row
    assert row["event_news_bundle"] == [
        {"title": "same-day news", "url": "https://example.invalid/news"}
    ]
    assert row["link_buffett"] == "https://example.invalid/7203"


def test_project_csv_row_does_not_fill_previous_calendar_news() -> None:
    csv_row = {
        "date": "2026-08-28",
        "code": "7203",
        "name": "Toyota",
        "z_turnover_60": 1.5,
        "rs31_topix": 0.11,
        "rs63_topix": 0.12,
        "rs126_topix": 0.13,
        "rs252_topix": 0.14,
        "rs_acceleration_topix": 0.01,
        "rs_acceleration_zscore_topix": 0.02,
        "rs_sma75_topix": 0.09,
        "event_news_1_title": "yesterday news",
    }
    row = project_csv_row(csv_row, bench="topix", as_of="2026-08-31")
    assert row["event_news_bundle"] is None


def test_window_series_last_bar_equals_as_of() -> None:
    axis = _axis()
    dates = ["2026-06-01"] + axis
    values = [0.0] + [0.2] * AXIS_LEN
    windowed = window_series_to_axis(
        dates,
        {"rs31_topix": values, "z_turnover_60": values, "rs_sma75_topix": values},
        axis,
        bench="topix",
    )
    assert len(windowed["rs31"]) == AXIS_LEN
    assert windowed["rs31"][-1] == pytest.approx(0.2)
    assert windowed["rs31"][0] == pytest.approx(0.2)


def test_fake_web_asof_commit_is_three_objects_unique_per_bench() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    as_of = _axis()[-1]
    result = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=as_of,
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
            repository="local",
            github_run_id=101,
            payloads={"topix": _payload("topix"), "nikkei": _payload("nikkei")},
        ),
        generation_store=store,
        r2_store=r2,
    )
    assert result.status == "ok"
    assert result.generation_id is not None
    assert len(result.object_keys) == WEB_ASOF_EXPECTED_OBJECT_COUNT
    topix_key = store.get_committed_web_asof_object_key(
        metric_set_version_id=_SET, benchmark="topix", as_of=as_of
    )
    nikkei_key = store.get_committed_web_asof_object_key(
        metric_set_version_id=_SET, benchmark="nikkei", as_of=as_of
    )
    assert topix_key and nikkei_key and topix_key != nikkei_key
    assert "benchmark=topix" in topix_key
    blob = r2.objects[topix_key]
    again = gunzip_bundle_bytes(blob)
    assert again["schema_id"] == SCHEMA_ID
    assert again["rows"][0]["code"] == "7203"
    assert again["series"]["7203"]["rs31"][-1] == again["rows"][0]["rs31"]


def test_fake_web_asof_retry_same_identity_is_idempotent() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    req = WebAsofGenerationRequest(
        as_of=_axis()[-1],
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
        repository="local",
        github_run_id=202,
        payloads={"topix": _payload("topix"), "nikkei": _payload("nikkei")},
    )
    first = run_web_asof_generation(req, generation_store=store, r2_store=r2)
    second = run_web_asof_generation(req, generation_store=store, r2_store=r2)
    assert first.status == "ok"
    assert second.status == "skipped"
    assert second.skipped is True
    assert first.generation_id == second.generation_id


def test_fake_web_asof_second_run_orphans_previous_and_keeps_unique_committed() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    as_of = _axis()[-1]
    first = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=as_of,
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
            repository="local",
            github_run_id=301,
            payloads={"topix": _payload("topix"), "nikkei": _payload("nikkei")},
        ),
        generation_store=store,
        r2_store=r2,
    )
    second = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=as_of,
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
            repository="local",
            github_run_id=302,
            payloads={"topix": _payload("topix", sma=0.3), "nikkei": _payload("nikkei", sma=0.3)},
        ),
        generation_store=store,
        r2_store=r2,
    )
    assert first.status == "ok" and second.status == "ok"
    assert first.generation_id != second.generation_id
    committed_bundles = [
        row
        for row in store.pending_objects.values()
        if row["object_kind"] == "web_asof_bundle" and row.get("status") == "committed"
    ]
    orphaned = [
        row
        for row in store.pending_objects.values()
        if row["object_kind"] == "web_asof_bundle" and row.get("status") == "orphan"
    ]
    assert len(committed_bundles) == 2
    assert len(orphaned) == 2
    assert store.get_committed_web_asof_object_key(
        metric_set_version_id=_SET, benchmark="topix", as_of=as_of
    ) == second.object_keys[0]


def test_web_asof_commit_does_not_orphan_snapshot() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    as_of = _axis()[-1]
    snap = store.begin_generation(
        BeginGenerationRequest(
            source=SourceRunIdentity(
                repository="local",
                workflow="daily.yml",
                github_run_id=401,
                metric_set_version_id=_SET,
                trade_date=as_of,
                mode="normal",
            ),
            artifact_profile=ArtifactProfile.SNAPSHOT_ONLY,
            expected_object_count=2,
            new_logical_digest="c" * 64,
        )
    )
    digest = "d" * 64
    snap_keys: list[str] = []
    for kind, key in (
        ("snapshot", f"derived-snapshots/snap-{uuid4()}.parquet"),
        ("snapshot_manifest", f"derived-snapshots/man-{uuid4()}.json"),
    ):
        snap_keys.append(key)
        store.register_pending_object(
            generation_id=snap.generation_id,
            object_kind=kind,
            object_key=key,
            logical_digest=digest,
            byte_sha256=digest,
            size_bytes=8,
            trade_date=as_of,
        )
        store.mark_object_uploaded(
            generation_id=snap.generation_id,
            object_key=key,
            byte_sha256=digest,
            size_bytes=8,
        )
    from stockradar.storage.derived_generation import compute_object_set_digest

    store.set_expected_object_set_digest(
        generation_id=snap.generation_id,
        expected_object_set_digest=compute_object_set_digest(snap_keys),
    )
    store.commit_generation(generation_id=snap.generation_id, new_logical_digest="c" * 64)
    result = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=as_of,
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
            repository="local",
            github_run_id=402,
            payloads={"topix": _payload("topix"), "nikkei": _payload("nikkei")},
        ),
        generation_store=store,
        r2_store=r2,
    )
    assert result.status == "ok"
    snap_rows = [
        row
        for row in store.pending_objects.values()
        if row["object_kind"] == "snapshot"
    ]
    assert snap_rows and all(row.get("status") == "committed" for row in snap_rows)
    assert store.get_committed_snapshot_digest(metric_set_version_id=_SET, trade_date=as_of) == "c" * 64


def test_bundle_lab_gzip_and_parse_slo() -> None:
    codes = [f"{i:04d}" for i in range(1, 201)]
    payload = _payload("topix", codes=codes)
    times: list[float] = []
    blob = b""
    for _ in range(20):
        blob, _key, _digest = encode_web_asof_bundle(payload)
        t0 = time.perf_counter()
        again = gunzip_bundle_bytes(blob)
        times.append(time.perf_counter() - t0)
        assert again["rows"][0]["code"] == "0001"
    assert len(blob) < GZIP_MAX_BYTES
    p95 = statistics.quantiles(times, n=20)[-1] if len(times) >= 20 else max(times)
    assert p95 < 2.0, f"p95 parse {p95:.4f}s exceeds 2.0s lab SLO"


def test_v11_shadow_generation_does_not_activate_registry() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    result = run_web_asof_generation(
        WebAsofGenerationRequest(
            as_of=_axis()[-1],
            metric_set_version_id=_SET,
            set_fingerprint=_FP,
            repository="shadow-local",
            github_run_id=501,
            payloads={"topix": _payload("topix"), "nikkei": _payload("nikkei")},
        ),
        generation_store=store,
        r2_store=r2,
    )
    assert result.status == "ok"
    generation = store.get_generation(result.generation_id or "")
    assert generation is not None
    assert generation.artifact_profile == ArtifactProfile.WEB_ASOF.value
    assert generation.status == "committed"
    assert store.committed_snapshot_digest_by_set_date == {}


def test_project_csv_row_rounds_bundle_floats() -> None:
    csv_row = {
        "date": "2026-08-31",
        "code": "7203",
        "name": "Toyota",
        "z_turnover_60": 1.123456789,
        "rs31_topix": 0.11,
        "rs63_topix": 0.12,
        "rs126_topix": 0.13,
        "rs252_topix": 0.14,
        "rs_acceleration_topix": 0.01,
        "rs_acceleration_zscore_topix": 0.02,
        "rs_sma75_topix": -0.006165236109645145,
    }
    row = project_csv_row(csv_row, bench="topix", as_of="2026-08-31")
    assert row["z_turnover_60"] == 1.123457
    assert row["rs_sma75"] == -0.006165
