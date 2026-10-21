#!/usr/bin/env python3
"""Offline simulator for the FlySky Remote Test Lab page.  NO ROS, NO SERIAL, NO RECEIVER, NO ROVER.

Serves the real web/v2 files and the real atlas_flysky_web API, fed by synthetic SBUS/iBUS frames.

    python3 sim_server.py --port 8097 --scenario no_source|waiting|garbage|live|stale|failsafe|frame_lost|ibus
Open http://127.0.0.1:8097/v2/flysky-testlab
Switch live:  curl 'http://127.0.0.1:8097/sim?scenario=live'
"""
import argparse
import json
import math
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts')]
import atlas_flysky_core as C      # noqa: E402
import atlas_flysky_web as W       # noqa: E402
import atlas_web_v2                # noqa: E402

SCENARIOS = ('no_source', 'waiting', 'garbage', 'live', 'stale', 'failsafe', 'frame_lost', 'ibus')


class FakeTransport:
    def __init__(self, sim):
        self.sim = sim

    def start(self, on_message):
        pass

    def publisher_count(self):
        return 0 if self.sim.scenario == 'no_source' else 1

    def stop(self):
        pass


class Sim:
    def __init__(self, scenario):
        self.scenario = scenario
        self.t0 = time.monotonic()
        self.svc = W.FlyskyService(lambda: FakeTransport(self), Path('/tmp/atlas_flysky_sim'), start_threads=True)
        threading.Thread(target=self.loop, daemon=True).start()

    def frame(self, t):
        sc = self.scenario
        ch = [C.SBUS_MID] * 16
        ch[0] = int(992 + 700 * math.sin(t * 0.9))          # right stick x (sim)
        ch[1] = int(992 + 600 * math.sin(t * 0.6 + 1))      # right stick y
        ch[2] = int(992 + 500 * math.sin(t * 0.4))          # left stick y
        ch[3] = int(992 + 650 * math.sin(t * 0.3 + 2))      # left stick x
        ch[4] = 172 if int(t / 4) % 2 else 1811             # 2-position switch
        ch[5] = (172, 992, 1811)[int(t / 3) % 3]            # 3-position switch
        if sc == 'ibus':
            return 'ibus', C.encode_ibus([int(1500 + (v - 992) * 500 / 819) for v in ch[:10]])
        return 'sbus', C.encode_sbus(ch, failsafe=(sc == 'failsafe'), frame_lost=(sc == 'frame_lost' and int(t) % 2 == 0))

    def loop(self):
        n = 0
        while True:
            time.sleep(0.02)
            t = time.monotonic() - self.t0
            sc = self.scenario
            if sc in ('no_source', 'waiting'):
                continue
            if sc == 'garbage':
                self.svc._on_message(json.dumps({'proto': 'sbus', 'hex': bytes(random.randrange(256) for _ in range(25)).hex()}))
                continue
            if sc == 'stale' and t > 6:
                continue
            proto, data = self.frame(t)
            self.svc._on_message(json.dumps({'proto': proto, 'hex': data.hex()}))
            n += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8097)
    ap.add_argument('--scenario', default='live', choices=SCENARIOS)
    a = ap.parse_args()
    sim = Sim(a.scenario)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            p = urlsplit(self.path)
            if p.path == '/sim':
                q = parse_qs(p.query)
                sim.scenario = q.get('scenario', [sim.scenario])[0]
                sim.t0 = time.monotonic()
                if q.get('reset'):
                    with sim.svc.lock:
                        sim.svc.lab = C.FlyskyLab()
                body = json.dumps({'scenario': sim.scenario}).encode()
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
