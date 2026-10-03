"""Contract: web-asof bundle builder and migration 020 tokens."""
from __future__ import annotations

from pathlib import Path

import pytest

from stockradar.jobs.write_web_asof_bundle import (
    build_web_asof_bundle_payload,
    encode_web_asof_bundle,
)
from stockradar.storage.web_asof_bundle import AXIS_LEN, SCHEMA_ID, gunzip_bundle_bytes

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]
_M020 = _REPO / "supabase" / "migrations" / "020_web_asof_object_kind.sql"
_M022 = _REPO / "supabase" / "migrations" / "022_web_asof_artifact_profile.sql"
_M023 = _REPO / "supabase" / "migrations" / "023_web_asof_commit_rpc.sql"
_M024 = _REPO / "supabase" / "migrations" / "024_web_asof_register_benchmark.sql"
_FP = "b" * 64
_SET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _payload():
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
    return build_web_asof_bundle_payload(
        as_of=axis[-1],
        benchmark="topix",
        metric_set_version_id=_SET,
        set_fingerprint=_FP,
        axis_dates=axis,
        rows=[row],
        series=series,
    )


def test_builder_encodes_gzip_key():
    payload = _payload()
    assert payload["schema_id"] == SCHEMA_ID
    blob, key, digest = encode_web_asof_bundle(payload)
    assert key.startswith("derived-web-asof/")
    assert "benchmark=topix" in key
    assert digest == __import__("hashlib").sha256(blob).hexdigest()
    again = gunzip_bundle_bytes(blob)
    assert again["rows"][0]["code"] == "7203"


def test_migration_020_tokens():
    raw = _M020.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    for token in (
        "web_asof_bundle",
        "web_asof_manifest",
        "benchmark",
        "derived_object_index_committed_web_asof_bundle",
    ):
        assert token in text
    assert "GRANT" not in text
    assert "GRANT SELECT" not in text
    assert "TO anon" not in text.lower()


def test_migration_022_tokens():
    raw = _M022.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    for token in (
        "web_asof",
        "derived_generation_runs_artifact_profile_check",
        "derived_object_index_committed_web_asof_manifest",
    ):
        assert token in text
    assert "GRANT" not in text
    assert "CREATE POLICY" not in text
    assert "activate_metric_set_cas" not in text


def test_migration_023_tokens():
    raw = _M023.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    for token in (
        "p_expected_old_digest is invalid for web_asof",
        "web_asof requires two bundles and one manifest",
        "GRANT EXECUTE ON FUNCTION public.commit_derived_generation",
        "TO service_role",
    ):
        assert token in text
    assert "TO anon" not in text.lower()
    assert "CREATE POLICY" not in text
    assert "activate_metric_set_cas" not in text


def test_migration_024_tokens():
    raw = _M024.read_bytes()
    assert bytes([0]) not in raw
    text = raw.decode("utf-8")
    for token in (
        "p_benchmark",
        "benchmark IS NOT DISTINCT FROM v_bench",
        "GRANT EXECUTE ON FUNCTION public.register_pending_derived_object",
        "TO service_role",
    ):
        assert token in text
    assert "TO anon" not in text.lower()
    assert "CREATE POLICY" not in text
    assert "activate_metric_set_cas" not in text
