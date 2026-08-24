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


ROOT = Path(__file__).resolve().parent
HTML = ROOT / "atlas_visual_cloud_dashboard.html"
DB = Path(os.environ.get("ATLAS_VISUAL_CLOUD_DB", "atlas_visual_cloud.sqlite3"))
TOKEN = os.environ.get("ATLAS_VISUAL_CLOUD_TOKEN", "")
PORT = int(os.environ.get("ATLAS_VISUAL_CLOUD_PORT", "8095"))
MAX_BODY = 2_000_000
LOCK = threading.Lock()
LATEST = {}


def connection():
    db = sqlite3.connect(DB, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, robot_id TEXT, observed_at REAL, git_version TEXT, failure_class TEXT, payload TEXT)")
    db.execute("CREATE INDEX IF NOT EXISTS snapshots_robot_time ON snapshots(robot_id, observed_at)")
    db.commit()
    return db


def store(value):
    robot = str(value.get("robot_id", "unknown"))[:100]
    encoded = json.dumps(value, separators=(",", ":"))
    with LOCK:
        LATEST[robot] = value
    db = connection()
    db.execute("INSERT INTO snapshots(robot_id,observed_at,git_version,failure_class,payload) VALUES(?,?,?,?,?)", (robot, float(value.get("observed_at", time.time())), str(value.get("git_version", ""))[:100], str(value.get("failure_class", "UNKNOWN"))[:40], encoded))
    db.execute("DELETE FROM snapshots WHERE id IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT -1 OFFSET 86400)")
    db.commit(); db.close()


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
        if path == "/": return self.reply(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/v1/robots":
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
