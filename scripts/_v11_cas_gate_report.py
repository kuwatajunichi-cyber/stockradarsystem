"""Numeric/purity/capacity report that must pass before activate_metric_set_cas.

Does not CAS. Does not write derived-series.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from stockradar.metrics.catalog_bind import inherited_definition_fingerprints_match
from stockradar.metrics.registry_spec import load_metric_set_spec
from stockradar.storage.phase45_budget import (
    DEFAULT_PATH_B_METRIC_SET_VERSIONS,
    R2_WARN_BYTES,
    SUPABASE_WARN_BYTES,
)
from stockradar.storage.web_asof_bundle import SMA75_NON_NULL_RATE_MIN, sma75_non_null_rate

_FREEZE = _REPO / "data" / "cache" / "web_asof_oneshot" / "freeze.sqlite"
_V1 = _REPO / "config" / "metrics" / "metric_set_v1.yaml"
_V11 = _REPO / "config" / "metrics" / "metric_set_v1_1.yaml"
_V1_FREE = _REPO / "config" / "metrics" / "metric_set_v1_free.yaml"


def _sma_from_freeze(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        n_rows = int(conn.execute("SELECT n_rows FROM meta LIMIT 1").fetchone()[0])
        topix: list = []
        nikkei: list = []
        for (_code, payload_json) in conn.execute("SELECT code, payload_json FROM rows"):
            row = json.loads(payload_json)
            topix.append(row.get("rs_sma75_topix"))
            nikkei.append(row.get("rs_sma75_nikkei"))
    finally:
        conn.close()
    return {
        "n_rows": n_rows,
        "topix_non_null_rate": sma75_non_null_rate(topix),
        "nikkei_non_null_rate": sma75_non_null_rate(nikkei),
        "topix_ok": sma75_non_null_rate(topix) >= SMA75_NON_NULL_RATE_MIN and bool(topix),
        "nikkei_ok": sma75_non_null_rate(nikkei) >= SMA75_NON_NULL_RATE_MIN and bool(nikkei),
        "min_rate": SMA75_NON_NULL_RATE_MIN,
    }


def main() -> int:
    v1 = load_metric_set_spec(_V1)
    v11 = load_metric_set_spec(_V11)
    free = load_metric_set_spec(_V1_FREE)
    inherited = inherited_definition_fingerprints_match(v1, v11)
    inherited_free = inherited_definition_fingerprints_match(free, v11)
    sma = _sma_from_freeze(_FREEZE) if _FREEZE.is_file() else {"error": "freeze sqlite missing"}
    web_asof_60_est = 60 * 2 * 5 * 1024 * 1024
    payload = {
        "status": "ok",
        "v11_set_key": v11.set_key,
        "v11_set_fingerprint": v11.set_fingerprint,
        "v11_member_count": len(v11.members),
        "v1_member_count": len(v1.members),
        "v1_free_member_count": len(free.members),
        "inherited_v1_mismatches": inherited,
        "inherited_v1_free_mismatches": inherited_free,
        "sma75": sma,
        "capacity": {
            "catalog_versions_planned": DEFAULT_PATH_B_METRIC_SET_VERSIONS,
            "derived_series_backfill": False,
            "web_asof_60_byte_estimate": web_asof_60_est,
            "r2_warn_bytes": R2_WARN_BYTES,
            "supabase_warn_bytes": SUPABASE_WARN_BYTES,
            "web_asof_60_under_r2_warn": web_asof_60_est < R2_WARN_BYTES,
        },
        "cas_gates": {
            "inherited_v1_ok": inherited == [],
            "sma75_ok": bool(sma.get("topix_ok") and sma.get("nikkei_ok")),
            "capacity_ok": web_asof_60_est < R2_WARN_BYTES,
        },
    }
    gates = payload["cas_gates"]
    payload["cas_allowed"] = all(gates.values())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["cas_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
