"""Gap token rewrite for committed web-asof bundles. Secrets 不要."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from stockradar.jobs.swap_web_asof_gap_tokens import commit_swapped_as_of
from stockradar.jobs.write_web_asof_bundle import run_web_asof_generation, WebAsofGenerationRequest
from stockradar.storage.derived_generation import FakeMetricGenerationStore
from stockradar.storage.r2_object_store import FakeR2ObjectStore
from stockradar.storage.web_asof_bundle import (
    AXIS_LEN,
    SCHEMA_ID,
    gzip_bundle_bytes,
    gunzip_bundle_bytes,
    physical_bundle_object_key,
    sha256_hex,
)
from stockradar.storage.web_asof_gap_token_swap import (
    GENERATOR_FIX_COMMITTED_AT_UTC,
    SWAP_WORKFLOW,
    BundlePointer,
    GapTokenSwapError,
    latest_pre_cutoff_pointers,
    pair_as_of_pointers,
    sakata_gap_token,
    series_canonical_bytes,
    swap_gap_bundle,
    swap_gap_label_tokens,
    swap_gap_price_text,
    swap_github_run_id,
)

pytestmark = pytest.mark.unit

_FP = "c" * 64
_SET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _payload(*, labels: str, price_text: str, extra_row: dict | None = None) -> dict:
    axis = [f"2026-07-{i:02d}" for i in range(1, 31)] + [
        f"2026-08-{i:02d}" for i in range(1, 31)
    ]
    axis = axis[:AXIS_LEN]
    zeros = [0.2] * AXIS_LEN
    row = {
        "code": "7203",
        "name": "Toyota",
        "z_turnover_60": 0.2,
        "rs_acceleration": 0.2,
        "rs_acceleration_zscore": 0.2,
        "rs31": 0.2,
        "rs63": 0.2,
        "rs126": 0.2,
        "rs252": 0.2,
        "rs_sma75": 0.2,
        "candle_labels": labels,
        "price_text": price_text,
        "research_prompt_block": "keep-me",
    }
    series = {
        "7203": {
            "z_turnover_60": list(zeros),
            "rs_acceleration": list(zeros),
            "rs_acceleration_zscore": list(zeros),
            "rs31": list(zeros),
            "rs63": list(zeros),
            "rs126": list(zeros),
            "rs252": list(zeros),
            "rs_sma75": list(zeros),
        }
    }
    rows = [row]
    if extra_row is not None:
        rows.append(extra_row)
        extra_code = str(extra_row["code"])
        series[extra_code] = copy.deepcopy(series["7203"])
    return {
        "schema_id": SCHEMA_ID,
        "as_of": axis[-1],
        "benchmark": "topix",
        "metric_set_version_id": _SET,
        "set_fingerprint": _FP,
        "axis_dates": axis,
        "rows": rows,
        "series": series,
        "csv_source": "enriched_csv",
    }


def test_swap_tokens_and_phrases() -> None:
    assert swap_gap_label_tokens("GAP_DOWN,RANGE_VERY_LARGE,DIR_BULL") == (
        "GAP_UP,RANGE_VERY_LARGE,DIR_BULL"
    )
    assert swap_gap_label_tokens("GAP_UP,BODY_LONG,DIR_BEAR") == "GAP_DOWN,BODY_LONG,DIR_BEAR"
    assert swap_gap_label_tokens("GAP_DOMINANT,BODY_LONG") == "GAP_DOMINANT,BODY_LONG"
    assert swap_gap_price_text("下窓＋<極大>長陽線") == "上窓＋<極大>長陽線"
    assert swap_gap_price_text("上窓＋<極大>長陰線") == "下窓＋<極大>長陰線"


def test_both_gap_tokens_fail() -> None:
    with pytest.raises(GapTokenSwapError):
        swap_gap_label_tokens("GAP_UP,GAP_DOWN,DIR_BULL")


def test_bundle_swap_keeps_series_and_research_copy() -> None:
    payload = _payload(
        labels="GAP_DOWN,RANGE_VERY_LARGE,WICK_UPPER_LONG,BODY_LONG,DIR_BULL",
        price_text="下窓＋<極大>長上ヒゲ長陽線",
    )
    original_series = payload["series"]
    original_bytes = series_canonical_bytes(payload)
    out, stats = swap_gap_bundle(payload)
    assert out["series"] is original_series
    assert series_canonical_bytes(out) == original_bytes
    assert out["rows"][0]["candle_labels"] == (
        "GAP_UP,RANGE_VERY_LARGE,WICK_UPPER_LONG,BODY_LONG,DIR_BULL"
    )
    assert out["rows"][0]["price_text"] == "上窓＋<極大>長上ヒゲ長陽線"
    assert out["rows"][0]["research_prompt_block"] == "keep-me"
    assert stats.rows_with_gap_token == 1
    assert stats.labels_changed == 1
    assert stats.price_text_changed == 1
    assert payload["rows"][0]["candle_labels"].startswith("GAP_DOWN")


def test_bundle_with_both_tokens_does_not_commit_payload() -> None:
    payload = _payload(labels="GAP_UP,GAP_DOWN", price_text="上窓＋下窓＋")
    with pytest.raises(GapTokenSwapError, match="both GAP_UP and GAP_DOWN"):
        swap_gap_bundle(payload)


def test_sakata_upward_window_is_gap_up() -> None:
    assert sakata_gap_token(prev_high=100.0, prev_low=98.0, today_high=103.0, today_low=101.0) == (
        "GAP_UP"
    )
    assert sakata_gap_token(prev_high=100.0, prev_low=98.0, today_high=97.0, today_low=95.0) == (
        "GAP_DOWN"
    )
    assert sakata_gap_token(prev_high=100.0, prev_low=98.0, today_high=101.0, today_low=97.0) is None


def test_latest_pre_cutoff_skips_post_fix_commits() -> None:
    rows = [
        {
            "trade_date": "2026-11-13",
            "benchmark": "topix",
            "object_key": "old-topix",
            "committed_at_utc": "2026-11-13T15:00:00+00:00",
        },
        {
            "trade_date": "2026-11-13",
            "benchmark": "nikkei",
            "object_key": "old-nikkei",
            "committed_at_utc": "2026-11-13T15:00:00+00:00",
        },
        {
            "trade_date": "2026-11-13",
            "benchmark": "topix",
            "object_key": "new-topix",
            "committed_at_utc": "2026-11-14T07:00:00+00:00",
        },
        {
            "trade_date": "2026-11-13",
            "benchmark": "nikkei",
            "object_key": "new-nikkei",
            "committed_at_utc": "2026-11-14T07:00:00+00:00",
        },
        {
            "trade_date": "2026-11-12",
            "benchmark": "topix",
            "object_key": "keep-topix",
            "committed_at_utc": "2026-11-12T06:00:00Z",
        },
        {
            "trade_date": "2026-11-12",
            "benchmark": "nikkei",
            "object_key": "keep-nikkei",
            "committed_at_utc": "2026-11-12T06:00:00Z",
        },
    ]
    pointers = latest_pre_cutoff_pointers(rows, cutoff=GENERATOR_FIX_COMMITTED_AT_UTC)
    assert ("2026-11-13", "topix") not in pointers
    assert pointers[("2026-11-12", "topix")].object_key == "keep-topix"
    pairs, missing = pair_as_of_pointers(pointers)
    assert missing == []
    assert [item[0] for item in pairs] == ["2026-11-12"]


def test_cutoff_is_the_generator_fix_merge() -> None:
    assert GENERATOR_FIX_COMMITTED_AT_UTC == datetime(
        2026, 11, 14, 6, 11, 49, tzinfo=timezone.utc
    )
    assert swap_github_run_id("2026-11-13") == 20261113


def _store_bundle(r2: FakeR2ObjectStore, payload: dict, *, bench: str) -> BundlePointer:
    payload = dict(payload)
    payload["benchmark"] = bench
    blob = gzip_bundle_bytes(payload)
    digest = sha256_hex(blob)
    key = physical_bundle_object_key(
        metric_set_version_id=_SET,
        benchmark=bench,
        as_of=payload["as_of"],
        generation_id="old-gen",
        digest=digest,
    )
    r2.put_create_only(key, blob, content_type="application/gzip")
    return BundlePointer(
        trade_date=payload["as_of"],
        benchmark=bench,
        object_key=key,
        committed_at_utc="2026-11-12T00:00:00+00:00",
    )


def test_commit_swapped_as_of_writes_new_generation() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    topix = _payload(
        labels="GAP_DOWN,RANGE_LARGE,DIR_BULL",
        price_text="下窓＋<大>陽線",
    )
    nikkei = dict(topix)
    nikkei["benchmark"] = "nikkei"
    topix_ptr = _store_bundle(r2, topix, bench="topix")
    nikkei_ptr = _store_bundle(r2, nikkei, bench="nikkei")
    result = commit_swapped_as_of(
        as_of=topix["as_of"],
        topix=topix_ptr,
        nikkei=nikkei_ptr,
        generation_store=store,
        r2_store=r2,
    )
    assert result.status == "ok"
    assert result.generation_id is not None
    new_key = store.get_committed_web_asof_object_key(
        metric_set_version_id=_SET, benchmark="topix", as_of=topix["as_of"]
    )
    assert new_key and new_key != topix_ptr.object_key
    rewritten = gunzip_bundle_bytes(r2.get_object(new_key))
    assert rewritten["rows"][0]["candle_labels"].startswith("GAP_UP,")
    assert rewritten["rows"][0]["price_text"].startswith("上窓＋")
    assert r2.get_object(topix_ptr.object_key)  # old gzip remains


def test_failed_identity_is_not_retried() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    payload = _payload(labels="GAP_DOWN", price_text="下窓＋")
    topix_ptr = _store_bundle(r2, payload, bench="topix")
    nikkei = dict(payload)
    nikkei["benchmark"] = "nikkei"
    nikkei_ptr = _store_bundle(r2, nikkei, bench="nikkei")
    skipped = commit_swapped_as_of(
        as_of=payload["as_of"],
        topix=topix_ptr,
        nikkei=nikkei_ptr,
        generation_store=store,
        r2_store=r2,
        existing_status="failed",
    )
    assert skipped.skipped is True
    assert skipped.reason == "identity_failed"
    assert store.get_committed_web_asof_object_key(
        metric_set_version_id=_SET, benchmark="topix", as_of=payload["as_of"]
    ) is None


def test_same_identity_second_commit_is_skipped() -> None:
    store = FakeMetricGenerationStore()
    r2 = FakeR2ObjectStore()
    payload = _payload(labels="GAP_DOWN", price_text="下窓＋")
    nikkei = dict(payload)
    nikkei["benchmark"] = "nikkei"
    req = WebAsofGenerationRequest(
        as_of=payload["as_of"],
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
        repository="kuwatajunichi-cyber/stockradarsystem",
        github_run_id=swap_github_run_id(payload["as_of"]),
        payloads={"topix": payload, "nikkei": nikkei},
        workflow=SWAP_WORKFLOW,
        mode="replay",
        enforce_sma75=False,
    )
    first = run_web_asof_generation(req, generation_store=store, r2_store=r2)
    second = run_web_asof_generation(req, generation_store=store, r2_store=r2)
    assert first.status == "ok"
    assert second.skipped is True
