#!/usr/bin/env python3
"""Offline simulator for the Motor & Encoder Test Lab page.  NO ROS, NO SERIAL, NO ROVER.

Serves the real web/v2 files and the real atlas_testlab_web API on localhost, fed by a simulated encoder stream and
(optionally) a simulated lifted-drive OWNER that is the real LiftedDriveCommission state machine.  Use it to try the
page on a PC/phone before anything is deployed, and for screenshots/tests.

    python3 sim_server.py --port 8099 --scenario rest|rolling|m3_forward_loss|m2_reversed|stale --owner none|ready
Open http://127.0.0.1:8099/v2/testlab
Change scenario live:  curl 'http://127.0.0.1:8099/sim?scenario=rolling&owner=ready'
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
import atlas_testlab_web as W   # noqa: E402
import atlas_web_v2             # noqa: E402
from test_testlab_core import FakeOwner   # noqa: E402  (the real state machine on a settable clock)
from test_testlab_web import FakeTransport  # noqa: E402

C = 0.392699
SPEEDS = {  # forward turns per second for M1..M4
    'rest': [0, 0, 0, 0], 'rolling': [0.9, 0.9, 0.9, 0.9], 'm3_forward_loss': [0.9, 0.9, 0.09, 0.9],
    'm2_reversed': [0.9, -0.5, 0.9, 0.9], 'stale': [0, 0, 0, 0]}


class Sim:
    def __init__(self, scenario, owner):
        self.scenario, self.owner_mode = scenario, owner
        self.owner = FakeOwner()
        self.owner.now = time.monotonic()
        self.tr = FakeTransport(self.owner)
        self.svc = W.TestLabService(lambda: self.tr, Path('/tmp/atlas_testlab_sim'), start_threads=True)
        self.dist = [0.0] * 4
        self.seq = 0
        self.stop = threading.Event()
        self.owner.entry_stable = 8.0
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        last = time.monotonic()
        while not self.stop.wait(0.05):
            now = time.monotonic()
            dt, last = now - last, now
            self.owner.now = now
            self.owner.core.tick(now, self.owner.snap())
            sp = SPEEDS.get(self.scenario, SPEEDS['rest'])
            self.dist = [self.dist[i] + sp[i] * C * dt for i in range(4)]
            if self.scenario != 'stale':
                self.seq += 1
                raw = [int(self.dist[i] / C * 2200) * (1, -1, 1, -1)[i] for i in range(4)]
                self.svc._on_update(json.dumps({'sequence': self.seq, 'raw_counts': raw, 'wheel_distances_m': self.dist,
                                                'packet_fresh': True, 'packet_age_s': 0.02, 'accepted_channels': [1, 2, 3, 4],
                                                'rejected_channels': []}))
                self.svc._on_health(json.dumps({'state': 'READY', 'consensus_state': 'AVAILABLE',
                                                'last_change_age_s': [0.1, 0.1, 0.1, 0.1]}))
            if self.owner_mode == 'ready':
                self.owner.raw_enabled = self.owner.cut_ready = True
                self.svc._on_status(json.dumps(self.owner.status()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8099)
    ap.add_argument('--scenario', default='rest', choices=sorted(SPEEDS))
    ap.add_argument('--owner', default='none', choices=('none', 'ready'))
    a = ap.parse_args()
    sim = Sim(a.scenario, a.owner)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            p = urlsplit(self.path)
            if p.path == '/sim':
                q = parse_qs(p.query)
                sim.scenario = q.get('scenario', [sim.scenario])[0]
                sim.owner_mode = q.get('owner', [sim.owner_mode])[0]
                if 'latched' in q:
                    sim.owner.stop_latched = q['latched'][0] == '1'
                body = json.dumps({'scenario': sim.scenario, 'owner': sim.owner_mode, 'latched': sim.owner.stop_latched}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
                return
            if W.serve(self, service=sim.svc):
                return
            if atlas_web_v2.handles(self.path):
                atlas_web_v2.serve(self)
                return
            self.send_error(404)

        def do_POST(self):
            if W.serve(self, post=True, service=sim.svc):
                return
            n = int(self.headers.get('Content-Length', '0'))
            self.rfile.read(n)
            body = b'{"message":"Simulated stop (nothing connected)."}'
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)

    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
