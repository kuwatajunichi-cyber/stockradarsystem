#!/usr/bin/env python3
"""Serve prototype static UI + /api/* from as-of SQLite snapshots on 127.0.0.1 only."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from stockradar.prototype_web_ui_asof.isolation import validate_bind_host

WEB_ROOT = _REPO / "prototypes" / "web-ui-asof" / "web"
ASOF_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.sqlite$")


def discover_asof_catalog(sqlite_dir: Path) -> dict[str, Path]:
    catalog: dict[str, Path] = {}
    for path in sorted(sqlite_dir.glob("*.sqlite")):
        m = ASOF_NAME.match(path.name)
        if m and path.is_file() and path.stat().st_size > 0:
            catalog[m.group(1)] = path.resolve()
    return catalog


class PrototypeHandler(SimpleHTTPRequestHandler):
    catalog: dict[str, Path]
    default_as_of: str

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(WEB_ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        if parsed.path in ("/favicon.ico", "/favicon.png"):
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        if code == 404 and not urlparse(self.path).path.startswith("/api/"):
            body = (
                "<!DOCTYPE html><meta charset=utf-8>"
                "<title>not found</title>"
                "<body style='font:14px/1.5 sans-serif;padding:1.5rem'>"
                "<h1>404 — この URL には UI がありません</h1>"
                "<p>表示は <a href='/'><strong>http://127.0.0.1:8765/</strong></a> を開いてください。</p>"
                f"<p style='color:#666'>requested: {self.path}</p>"
                "</body>"
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().send_error(code, message=message, explain=explain)

    def _handle_api(self, parsed) -> None:
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/dates":
                payload = {
                    "dates": list(self.catalog.keys()),
                    "default": self.default_as_of,
                }
            elif parsed.path == "/api/meta":
                payload = self._meta(self._as_of(qs))
            elif parsed.path == "/api/rows":
                payload = self._rows(self._as_of(qs))
            elif parsed.path == "/api/series":
                codes: list[str] = []
                if "codes" in qs:
                    for chunk in qs["codes"]:
                        codes.extend([c.strip().zfill(4) for c in chunk.split(",") if c.strip()])
                payload = self._series(self._as_of(qs), codes)
            else:
                self.send_error(404, "unknown api")
                return
        except Exception as exc:
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _as_of(self, qs: dict[str, list[str]]) -> str:
        as_of = (qs.get("as_of") or [self.default_as_of])[0]
        if as_of not in self.catalog:
            raise ValueError(f"unknown as_of={as_of!r}; available={list(self.catalog)}")
        return as_of

    def _conn(self, as_of: str) -> sqlite3.Connection:
        path = self.catalog[as_of]
        return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)

    def _meta(self, as_of: str) -> dict:
        with self._conn(as_of) as conn:
            row = conn.execute(
                "SELECT as_of, source_csv_sha256, freeze_utc, n_rows, n_excluded, axis_dates_json, note FROM meta LIMIT 1"
            ).fetchone()
        if not row:
            raise RuntimeError("meta empty")
        return {
            "as_of": row[0],
            "source_csv_sha256": row[1],
            "freeze_utc": row[2],
            "n_rows": row[3],
            "n_excluded": row[4],
            "axis_dates": json.loads(row[5]),
            "note": row[6],
            "available_dates": list(self.catalog.keys()),
            "bind": "127.0.0.1",
            "track_d": False,
        }

    def _rows(self, as_of: str) -> dict:
        with self._conn(as_of) as conn:
            rows = conn.execute("SELECT code, payload_json FROM rows ORDER BY code").fetchall()
        return {"as_of": as_of, "rows": [json.loads(payload) for _, payload in rows]}

    def _series(self, as_of: str, codes: list[str]) -> dict:
        if not codes:
            return {"as_of": as_of, "series": {}}
        placeholders = ",".join("?" for _ in codes)
        with self._conn(as_of) as conn:
            rows = conn.execute(
                f"SELECT code, metrics_json FROM series WHERE code IN ({placeholders})",
                codes,
            ).fetchall()
        return {"as_of": as_of, "series": {code: json.loads(payload) for code, payload in rows}}

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Prototype localhost serve (127.0.0.1 only)")
    p.add_argument(
        "--sqlite-dir",
        type=Path,
        default=None,
        help="Directory of YYYY-MM-DD.sqlite snapshots (prototype multi-as-of)",
    )
    p.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Single sqlite (also scans sibling YYYY-MM-DD.sqlite in the same directory)",
    )
    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)

    try:
        validate_bind_host(args.host)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.sqlite_dir is not None:
        sqlite_dir = args.sqlite_dir.resolve()
        default_as_of = None
    elif args.sqlite is not None:
        sqlite_path = args.sqlite.resolve()
        if not sqlite_path.is_file():
            print(f"FAIL: sqlite not found: {sqlite_path}", file=sys.stderr)
            return 1
        sqlite_dir = sqlite_path.parent
        m = ASOF_NAME.match(sqlite_path.name)
        default_as_of = m.group(1) if m else None
        # ensure the explicitly passed file is included even if name is not as-of shaped
        catalog_seed = discover_asof_catalog(sqlite_dir)
        if default_as_of is None:
            # fall back: read as_of from meta and map this file
            with sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True) as conn:
                default_as_of = conn.execute("SELECT as_of FROM meta LIMIT 1").fetchone()[0]
            catalog_seed[default_as_of] = sqlite_path
        catalog = catalog_seed
        if default_as_of not in catalog:
            catalog[default_as_of] = sqlite_path
    else:
        print("FAIL: provide --sqlite-dir or --sqlite", file=sys.stderr)
        return 1

    if args.sqlite_dir is not None:
        if not sqlite_dir.is_dir():
            print(f"FAIL: sqlite-dir not found: {sqlite_dir}", file=sys.stderr)
            return 1
        catalog = discover_asof_catalog(sqlite_dir)
        if not catalog:
            print(f"FAIL: no YYYY-MM-DD.sqlite in {sqlite_dir}", file=sys.stderr)
            return 1
        default_as_of = sorted(catalog.keys())[-1]

    if not WEB_ROOT.is_dir():
        print(f"FAIL: web root missing: {WEB_ROOT}", file=sys.stderr)
        return 1

    PrototypeHandler.catalog = catalog
    PrototypeHandler.default_as_of = default_as_of
    httpd = ThreadingHTTPServer((args.host, args.port), partial(PrototypeHandler))
    print(
        f"serving http://{args.host}:{args.port}/ "
        f"dates={list(catalog.keys())} default={default_as_of} (not Track D)"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
