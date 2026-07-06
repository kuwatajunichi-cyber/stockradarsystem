"""Apply Phase 3 Supabase migration."""
from __future__ import annotations
import os, sys
from pathlib import Path
from urllib.parse import quote_plus
_REPO = Path(__file__).resolve().parents[2]
MIGRATION = _REPO / "supabase/migrations/001_phase3_control_plane.sql"
def _load_dotenv():
    p = _REPO / ".env"
    if not p.is_file(): return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v = line.split("=",1); os.environ.setdefault(k.strip(), v.strip())
def main():
    _load_dotenv()
    ref = os.environ.get("SUPABASE_PROJECT_REF","").strip()
    pw = os.environ.get("SUPABASE_STOCK_RADAR_SYSTEM_PASSWORD","").strip()
    if not ref or not pw:
        print("error: SUPABASE_PROJECT_REF and SUPABASE_STOCK_RADAR_SYSTEM_PASSWORD required", file=sys.stderr); return 1
    import psycopg
    sql = MIGRATION.read_text(encoding="utf-8")
    conninfo = f"postgresql://postgres:{quote_plus(pw)}@db.{ref}.supabase.co:5432/postgres?sslmode=require"
    print("Connecting...")
    with psycopg.connect(conninfo, connect_timeout=30) as conn:
        conn.autocommit = True
        with conn.cursor() as cur: cur.execute(sql)
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name = ANY(%s) ORDER BY 1", (["runs","artifact_index","cache_index","cache_pointers"],))
            tables = [r[0] for r in cur.fetchall()]
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid WHERE n.nspname='public' AND p.proname='commit_fixed_cache'")
            rpc = cur.fetchone() is not None
    print("Tables:", tables); print("RPC:", rpc)
    if len(tables)!=4 or not rpc: print("error: verify failed", file=sys.stderr); return 1
    print("migration ok"); return 0
if __name__=="__main__": raise SystemExit(main())
