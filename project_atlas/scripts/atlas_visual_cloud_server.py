#!/usr/bin/env python3
"""Authenticated, read-only ATLAS Visual Cloud API and dashboard server."""

import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_visual_cloud_core import history_row, persist_due  # noqa: E402


ROOT = Path(__file__).resolve().parent
HTML = ROOT / "atlas_visual_cloud_dashboard.html"
# The unit's ATLAS_VISUAL_CLOUD_DB names the legacy full-snapshot history (25 GB, Sep 25 - Oct 4
# 2026). It is preserved untouched and never opened. Bounded history goes to a separate file.
LEGACY_DB = Path(os.environ.get("ATLAS_VISUAL_CLOUD_DB", "atlas_visual_cloud.sqlite3"))
DB = Path(os.environ.get("ATLAS_VISUAL_CLOUD_HISTORY_DB") or LEGACY_DB.with_name("history_bounded.sqlite3"))
if DB.resolve() == LEGACY_DB.resolve():
    DB = LEGACY_DB.with_name("history_bounded.sqlite3")
HISTORY_PERSIST_S = float(os.environ.get("ATLAS_VISUAL_CLOUD_HISTORY_PERSIST_S", "60"))
HISTORY_FAILURE_PERSIST_S = float(os.environ.get("ATLAS_VISUAL_CLOUD_HISTORY_FAILURE_PERSIST_S", "10"))
HISTORY_MAX_BYTES = int(float(os.environ.get("ATLAS_VISUAL_CLOUD_HISTORY_MAX_MB", "256")) * 1024 * 1024)
LAST_VIEWER = None          # monotonic time the preview page last asked for data
LAST_FAILURE_PERSIST = None
TOKEN = os.environ.get("ATLAS_VISUAL_CLOUD_TOKEN", "")
PORT = int(os.environ.get("ATLAS_VISUAL_CLOUD_PORT", "8095"))
MAX_BODY = 2_000_000
LOCK = threading.Lock()
LATEST = {}
RETENTION_ROWS = 86_400
PRUNE_INTERVAL_S = 60.0
LAST_PRUNE = 0.0
LAST_PERSIST = 0.0
NORMAL_PERSIST_S = float(os.environ.get("ATLAS_VISUAL_CLOUD_NORMAL_PERSIST_S", "1.0"))
HEAVY_PERSIST_S = float(os.environ.get("ATLAS_VISUAL_CLOUD_HEAVY_PERSIST_S", "10.0"))
HEAVY_LOAD = float(os.environ.get(
    "ATLAS_VISUAL_CLOUD_HEAVY_LOAD", str(max(4.0, (os.cpu_count() or 4) * 1.25))
))


def persistence_interval(value):
    """Reduce historical writes under load; never reduce live API updates."""
    system = value.get("system", {}) if isinstance(value, dict) else {}
    load = system.get("load", []) if isinstance(system, dict) else []
    try:
        load_1m = float(load[0]) if load else 0.0
        ram = float(system.get("ram_used_pct", 0.0))
        temperature = float(system.get("temperature_c", 0.0))
    except (TypeError, ValueError, IndexError):
        load_1m = ram = temperature = 0.0
    traffic = value.get("traffic", {}) if isinstance(value, dict) else {}
    mission = traffic.get("/atlas/mission_status", {}) if isinstance(traffic, dict) else {}
    mission_value = str(mission.get("value", "")).upper() if isinstance(mission, dict) else ""
    heavy = (
        load_1m >= HEAVY_LOAD
        or ram >= 85.0
        or temperature >= 75.0
        or any(word in mission_value for word in ("MAPPING", "NAVIGATING", "RETURNING"))
    )
    return HEAVY_PERSIST_S if heavy else NORMAL_PERSIST_S


def connection():
    fresh = not DB.exists()
    db = sqlite3.connect(DB, timeout=10)
    if fresh:
        db.execute("PRAGMA auto_vacuum=INCREMENTAL")   # lets pruning return space to the filesystem
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, robot_id TEXT, observed_at REAL, git_version TEXT, failure_class TEXT, payload TEXT)")
    db.execute("CREATE INDEX IF NOT EXISTS snapshots_robot_time ON snapshots(robot_id, observed_at)")
    db.commit()
    return db


def store(value):
    """Live view: every ingest replaces LATEST in memory. History: a bounded row (history_row)
    at most every HISTORY_PERSIST_S (failures every HISTORY_FAILURE_PERSIST_S), capped at
    HISTORY_MAX_BYTES and RETENTION_ROWS."""
    global LAST_PERSIST, LAST_PRUNE, LAST_FAILURE_PERSIST
    robot = str(value.get("robot_id", "unknown"))[:100]
    now = time.monotonic()
    failure = str(value.get("failure_class", "UNKNOWN"))[:40]
    with LOCK:
        LATEST[robot] = value
        interval = max(HISTORY_PERSIST_S, persistence_interval(value))
        if not persist_due(LAST_PERSIST or None, LAST_FAILURE_PERSIST, now, failure, interval, HISTORY_FAILURE_PERSIST_S):
            return
        if failure in ("", "NONE"):
            LAST_PERSIST = now
        else:
            LAST_FAILURE_PERSIST = now
    encoded = json.dumps(history_row(value), separators=(",", ":"))
    db = connection()
    db.execute("INSERT INTO snapshots(robot_id,observed_at,git_version,failure_class,payload) VALUES(?,?,?,?,?)", (robot, float(value.get("observed_at", time.time())), str(value.get("git_version", ""))[:100], failure, encoded))
    if now - LAST_PRUNE >= PRUNE_INTERVAL_S:
        db.execute(
            "DELETE FROM snapshots WHERE id <= "
            "COALESCE((SELECT MAX(id) FROM snapshots), 0) - ?",
            (RETENTION_ROWS,),
        )
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        used = lambda: (db.execute("PRAGMA page_count").fetchone()[0] - db.execute("PRAGMA freelist_count").fetchone()[0]) * page_size
        while used() > HISTORY_MAX_BYTES:
            count = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            if count <= 1:
                break
            # Delete the oldest rows in batches, always keeping the newest row.
            db.execute("DELETE FROM snapshots WHERE id IN (SELECT id FROM snapshots ORDER BY id LIMIT ?)",
                       (max(1, min(500, count // 4)),))
            db.execute("PRAGMA incremental_vacuum")
        db.execute("PRAGMA incremental_vacuum")
        LAST_PRUNE = now
    db.commit(); db.close()


def note_viewer():
    global LAST_VIEWER
    with LOCK:
        LAST_VIEWER = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else payload.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def authorized(self):
        return bool(TOKEN) and self.headers.get("Authorization", "") == "Bearer " + TOKEN

    def do_POST(self):
        if self.path != "/api/v1/ingest": return self.reply(404, '{}')
        if not self.authorized(): return self.reply(401, '{"error":"unauthorized"}')
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY: return self.reply(413, '{"error":"invalid body"}')
        body = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip": body = gzip.decompress(body)
        value = json.loads(body)
        if value.get("authority") != "OBSERVABILITY_ONLY": return self.reply(400, '{"error":"invalid authority"}')
        store(value); self.reply(202, '{"accepted":true}')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            note_viewer(); return self.reply(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/v1/demand":
            # Agent-only (token): how long ago a browser last asked for data. Reveals nothing else.
            if not self.authorized(): return self.reply(401, '{"error":"unauthorized"}')
            with LOCK: last = LAST_VIEWER
            age = None if last is None else round(time.monotonic() - last, 1)
            return self.reply(200, json.dumps({"viewer_age_s": age}))
        if path == "/api/v1/robots":
            note_viewer()
            with LOCK: value = list(LATEST.values())
            return self.reply(200, json.dumps(value))
        if path.startswith("/api/v1/history/"):
            robot = path.rsplit("/", 1)[-1]
            db = connection(); rows = db.execute("SELECT payload FROM snapshots WHERE robot_id=? ORDER BY observed_at DESC LIMIT 600", (robot,)).fetchall(); db.close()
            return self.reply(200, "[" + ",".join(x[0] for x in reversed(rows)) + "]")
        return self.reply(404, '{}')

    def do_PUT(self): self.reply(405, '{"error":"read only"}')
    def do_DELETE(self): self.reply(405, '{"error":"read only"}')
    def log_message(self, fmt, *args): pass


def main():
    if not TOKEN: raise SystemExit("ATLAS_VISUAL_CLOUD_TOKEN must be set")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"ATLAS Visual Cloud read-only API listening on 127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__": main()
