"""Measure Phase 4.5 Supabase budget on local PostgreSQL (Blocker 4).

Applies migrations 001-005, seeds full-scale latest projection fixture, records
pg_database_size and table sizes. Secrets-free; uses local Postgres only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import numpy as np

from stockradar.storage.phase45_budget import (
    BUDGET_SCHEMA_VERSION,
    SUPABASE_WARN_BYTES,
    within_free_tier,
)

_REPO = Path(__file__).resolve().parents[2]
_MIGRATIONS = (
    "001_phase3_control_plane.sql",
    "002_phase4_control_plane.sql",
    "003_p0_control_plane_hardening.sql",
    "004_phase45_metric_registry.sql",
    "005_phase45_metric_registry_hardening.sql",
)

_BOOTSTRAP_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$
BEGIN
  CREATE ROLE anon NOLOGIN;
  CREATE ROLE authenticated NOLOGIN;
  CREATE ROLE service_role NOLOGIN BYPASSRLS;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
GRANT USAGE ON SCHEMA public TO service_role, anon, authenticated;
"""

_DEFAULT_DB = "phase45_budget_measure"


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out[:40] if out else "unknown"
    except Exception:
        return "unknown"


def _connect(admin_url: str, database: str):
    import psycopg

    base = admin_url.rsplit("/", 1)[0]
    admin_db_url = f"{base}/postgres"
    with psycopg.connect(admin_db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{database}"')
            cur.execute(f'CREATE DATABASE "{database}"')
    target = f"{base}/{quote_plus(database)}"
    return psycopg.connect(target)


def _apply_migrations(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_BOOTSTRAP_SQL)
    conn.commit()
    for name in _MIGRATIONS:
        sql = (_REPO / "supabase/migrations" / name).read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def _sha256_hex(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seed_fixture(
    conn,
    *,
    symbols: int,
    metrics: int,
    seed: int,
    trade_date: date,
) -> dict[str, str]:
    rng = np.random.default_rng(seed)
    set_fp = "b" * 64
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (workflow, github_run_id, run_date, status, finished_at_utc)
            VALUES ('phase45_budget_measure', 1, %s, 'success', now())
            RETURNING id
            """,
            (trade_date,),
        )
        run_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO metric_set_versions (
              set_key, lifecycle_status, set_fingerprint, source_run_id, writer_workflow
            )
            VALUES ('budget_fixture', 'draft', %s, %s, 'phase45_budget_measure')
            RETURNING id
            """,
            (set_fp, run_id),
        )
        set_id = cur.fetchone()[0]

        for m in range(metrics):
            key = f"metric_{m:02d}"
            cur.execute(
                """
                INSERT INTO metric_definitions (metric_key, display_name, value_type, unit, description)
                VALUES (%s, %s, 'float', 'ratio', 'budget fixture')
                ON CONFLICT (metric_key) DO NOTHING
                """,
                (key, key),
            )
            fp = _sha256_hex({"metric_key": key, "seed": seed})
            cur.execute(
                """
                INSERT INTO metric_versions (
                  metric_key, version_label, parameters, required_inputs, min_history_days,
                  missing_policy, definition_canonical, definition_fingerprint
                )
                VALUES (
                  %s, 'v1', '{}'::jsonb, '[]'::jsonb, 0,
                  '{}'::jsonb, '{}'::jsonb, %s
                )
                RETURNING id
                """,
                (key, fp),
            )
            metric_version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO metric_set_members (metric_set_version_id, metric_version_id, ordinal)
                VALUES (%s, %s, %s)
                """,
                (set_id, metric_version_id, m),
            )

        cur.execute(
            """
            SELECT transition_metric_set(%s, 'draft', 'shadow')
            """,
            (set_id,),
        )
        cur.execute(
            """
            SELECT activate_metric_set_cas(%s, %s, 'phase45_budget_measure', %s)
            """,
            (None, set_id, 1),
        )

        digest = _sha256_hex({"seed": seed, "metrics": metrics})
        for sym_idx in range(symbols):
            code = f"{7200 + sym_idx:04d}"
            values = {f"metric_{m:02d}": float(rng.uniform(0.0, 100.0)) for m in range(metrics)}
            cur.execute(
                """
                INSERT INTO latest_derived_observations (
                  instrument_code, metric_set_version_id, trade_date,
                  values_json, logical_digest, source_run_id
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (code, set_id, trade_date, json.dumps(values), digest, run_id),
            )
    conn.commit()
    return {"metric_set_version_id": str(set_id), "run_id": str(run_id)}


def _measure(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        database_bytes = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT c.relname, pg_total_relation_size(c.oid)::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY 1
            """
        )
        table_bytes = {name: int(size) for name, size in cur.fetchall()}

        cur.execute(
            """
            SELECT COALESCE(avg(pg_column_size(t.*)), 0)::float
            FROM latest_derived_observations t
            """
        )
        latest_row_avg = float(cur.fetchone()[0])

        cur.execute("SELECT count(*) FROM latest_derived_observations")
        latest_rows = int(cur.fetchone()[0])
    latest_table = table_bytes.get("latest_derived_observations", 0)
    registry_tables = sum(
        table_bytes.get(name, 0)
        for name in (
            "metric_definitions",
            "metric_versions",
            "metric_set_versions",
            "metric_set_members",
            "active_metric_set",
            "derived_object_index",
        )
    )
    control_plane_tables = sum(
        size
        for name, size in table_bytes.items()
        if name
        not in {
            "metric_definitions",
            "metric_versions",
            "metric_set_versions",
            "metric_set_members",
            "active_metric_set",
            "derived_object_index",
            "latest_derived_observations",
        }
    )
    return {
        "database_bytes": database_bytes,
        "latest_projection_table_bytes": latest_table,
        "latest_projection_row_avg_bytes": int(round(latest_row_avg)),
        "latest_projection_rows": latest_rows,
        "registry_metadata_bytes": registry_tables,
        "control_plane_baseline_bytes": control_plane_tables,
        "tables": table_bytes,
    }


def build_report(
    *,
    symbols: int,
    metrics: int,
    seed: int,
    pg_url: str,
    postgres_version: str,
) -> dict:
    trade_date = date(2026, 6, 30)
    conn = _connect(pg_url, _DEFAULT_DB)
    try:
        _apply_migrations(conn)
        ids = _seed_fixture(
            conn, symbols=symbols, metrics=metrics, seed=seed, trade_date=trade_date
        )
        sizes = _measure(conn)
    finally:
        conn.close()

    supabase_projection = (
        sizes["latest_projection_row_avg_bytes"] * sizes["latest_projection_rows"]
    )
    ok, reasons = within_free_tier(
        supabase_projection_bytes=sizes["database_bytes"],
        r2_total_bytes=0,
    )
    notes = list(reasons)
    notes.append(
        "postgres_measurement uses pg_database_size after DDL apply + full-scale latest seed"
    )
    if sizes["database_bytes"] >= SUPABASE_WARN_BYTES:
        ok = False
    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        "measurement_kind": "postgres_local",
        "generator_git_sha": _git_sha(),
        "generator_seed": seed,
        "postgres_connection": pg_url.split("@")[-1],
        "postgres_version": postgres_version,
        "migrations_applied": list(_MIGRATIONS),
        "counts": {
            "symbols": symbols,
            "metrics": metrics,
            "latest_rows": sizes["latest_projection_rows"],
        },
        "ids": ids,
        "bytes": {
            **sizes,
            "supabase_projection_estimated": supabase_projection,
        },
        "verdict": {"within_free_tier": ok, "notes": notes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4.5 local Postgres budget measurement")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols", type=int, default=3000)
    parser.add_argument("--metrics", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--pg-url",
        default="postgresql://postgres:postgres@localhost:5432/postgres",
        help="Admin URL (database name replaced for measurement DB)",
    )
    args = parser.parse_args(argv)

    try:
        import psycopg
    except ImportError:
        print("error: psycopg required (pip install psycopg[binary])", file=sys.stderr)
        return 1

    with psycopg.connect(args.pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            pg_version = str(cur.fetchone()[0])

    report = build_report(
        symbols=args.symbols,
        metrics=args.metrics,
        seed=args.seed,
        pg_url=args.pg_url,
        postgres_version=pg_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "database_bytes": report["bytes"]["database_bytes"],
                "within_free_tier": report["verdict"]["within_free_tier"],
            }
        )
    )
    return 0 if report["verdict"]["within_free_tier"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
