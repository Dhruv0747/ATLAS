#!/usr/bin/env python3
"""SIMULATION ONLY: observer responsiveness and the /api/status failure mechanism under CPU oversubscription.

For each load level L (busy processes per CPU, nice 0, same priority as everything else) for SECONDS:
  * independent observer (atlas_safety_observer) at the deployer's 0.25 s cadence against fake_foxglove.py
    (a Python stand-in, i.e. harsher than the C++ bridge) + odom writer + base stand-in;
  * web mechanism replica: Python HTTP server with GIL-busy threads (like a 107-subscription rclpy executor);
    /status refreshes a 2 s cache synchronously by spawning `ip -4 -br addr`, `ip -j route get`, `ss -tn`
    (exactly what atlas_status_web.snapshot() does); /estop returns a cached dict (like /api/estop/state).
    A client polls both every 0.5 s with the deployer's 2 s timeout.
Prints one JSON summary. usage: observer_saturation.py [seconds] [levels...]
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import atlas_safety_observer as so  # noqa: E402

BUSY = 'import time\nwhile True:\n    pass\n'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


WEB = r'''
import http.server, json, subprocess, threading, time, sys
def run(cmd):
    try: return subprocess.check_output(cmd, text=True, timeout=2, stderr=subprocess.STDOUT)
    except Exception: return ""
cache = {"ts": 0.0}; lock = threading.Lock(); state = {"latched": True}
def busy():                      # stand-in for rclpy executor callbacks holding the GIL
    x = 0
    while True:
        for i in range(2000): x += i
        time.sleep(0.001)
for _ in range(int(sys.argv[2])): threading.Thread(target=busy, daemon=True).start()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/estop":
            body = json.dumps(state)
        else:
            with lock:
                if time.monotonic() - cache["ts"] >= 2.0:
                    cache["net"] = [run(["ip", "-4", "-br", "addr"]), run(["ip", "-j", "route", "get", "1.1.1.1"]),
                                    run(["ss", "-tn", "state", "established"])]
                    cache["ts"] = time.monotonic()
            body = json.dumps({"ros": state, "net": len(cache["net"])})
        b = body.encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''


def poll_web(port, path, stop, out):
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as r:
                r.read()
            out.append(time.monotonic() - t0)
        except Exception:
            out.append(None)                 # timeout/error
        stop.wait(max(0.0, 0.5 - (time.monotonic() - t0)))


def odom_writer(path, stop):
    while not stop.is_set():
        tmp = Path(str(path) + '.tmp')
        tmp.write_text('{"x": -0.0035, "y": 0.0, "yaw": 0.0}')
        os.replace(tmp, path)
        stop.wait(0.3)


def level(seconds, per_cpu, web_threads=40):
    d = Path(tempfile.mkdtemp())
    ctl = d / 'ctl.json'
    ctl.write_text('{}')
    fport, wport = free_port(), free_port()
    procs = [subprocess.Popen([sys.executable, str(HERE / 'fake_foxglove.py'), str(fport), str(ctl)]),
             subprocess.Popen([sys.executable, '-c', WEB, str(wport), str(web_threads)])]
    base = subprocess.Popen(['sleep', '600'])
    odom = d / 'odom.json'
    stop = threading.Event()
    threading.Thread(target=odom_writer, args=(odom, stop), daemon=True).start()
    load = []
    try:
        return _measure(seconds, per_cpu, fport, wport, base, odom, stop, load)
    finally:                                   # never leave load/bridge/web processes behind (also on errors)
        stop.set()
        for p in load + procs + [base]:
            if p.poll() is None:
                p.kill()
            p.wait()
        shutil.rmtree(d, ignore_errors=True)


def _measure(seconds, per_cpu, fport, wport, base, odom, stop, load):
    time.sleep(1.0)
    obs = so.SafetyObserver(port=fport, base_pid=base.pid, odom_path=odom).start()
    end = time.monotonic() + 3
    while time.monotonic() < end and not obs.evaluate()['ok']:
        time.sleep(0.1)
    ncpu = os.cpu_count()
    load.extend(subprocess.Popen([sys.executable, '-c', BUSY]) for _ in range(per_cpu * ncpu))
    lat = {'/status': [], '/estop': []}
    for path in lat:
        threading.Thread(target=poll_web, args=(wport, path, stop, lat[path]), daemon=True).start()
    rows = []
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        v = obs.evaluate()
        rows.append((v['mono'], v['ok'], {k: s['age_s'] for k, s in v['signals'].items()},
                     [k for k, s in v['signals'].items() if not s['ok']]))
        time.sleep(0.25)
    obs.stop()
    gaps = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    maxage = {}
    for _, _, ages, _ in rows:
        for k, a in ages.items():
            if a is not None:
                maxage[k] = max(maxage.get(k, 0.0), a)
    fails = {}
    for _, ok, _, bad in rows:
        for k in bad:
            fails[k] = fails.get(k, 0) + 1

    def summ(xs):
        ok = sorted(x for x in xs if x is not None)
        return {'n': len(xs), 'timeouts_or_errors': sum(1 for x in xs if x is None),
                'p50_s': round(ok[len(ok) // 2], 3) if ok else None,
                'p95_s': round(ok[int(len(ok) * 0.95)], 3) if ok else None, 'max_s': round(max(ok), 3) if ok else None}
    return {'busy_per_cpu': per_cpu, 'cpus': ncpu, 'observer': {
                'evaluations': len(rows), 'ok_fraction': round(sum(r[1] for r in rows) / len(rows), 4),
                'max_eval_gap_s': round(max(gaps), 3), 'p99_eval_gap_s': round(sorted(gaps)[int(len(gaps) * 0.99)], 3),
                'max_signal_age_s': {k: round(v, 3) for k, v in sorted(maxage.items())}, 'not_ok_counts': fails},
            'web_replica': {k: summ(v) for k, v in lat.items()}}


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    levels = [int(x) for x in sys.argv[2:]] or [0, 1, 2, 4, 8]
    print(json.dumps([level(seconds, L) for L in levels], indent=1))


if __name__ == '__main__':
    main()
