"""Stage31b: the Vision Lab must not show the previous session's state as the new one after Start.
Headless Chromium against a scripted server (no Jetson, ROS or camera). Skips when playwright is unavailable."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

V2 = Path(__file__).resolve().parents[1] / 'web/v2'
LIM = {'cpu_percent': 75, 'ram_percent': 80, 'temperature_c': 70}
OLD = {'state': 'OFF', 'worker_pid': 111, 'driver_pid': 112, 'driver_stopped': True, 'limits': LIM, 'reason': 'viewer paused or closed',
       'resources': {'cpu_percent': 68.6, 'ram_percent': 70, 'thermal_c': {'cpu': 60.5}}}
NEW_CHECK = {'state': 'CHECKING', 'worker_pid': 222, 'limits': LIM, 'resources': {'cpu_percent': 64.0, 'ram_percent': 69, 'thermal_c': {'cpu': 60}}}
NEW_BLOCK = {'state': 'RESOURCE BLOCKED', 'worker_pid': 222, 'driver_pid': 223, 'driver_stopped': True, 'limits': LIM,
             'failed_resources': {'cpu': 76.0}, 'reason': 'RESOURCE BLOCKED: CPU', 'resources': {'cpu_percent': 64.5, 'ram_percent': 72, 'thermal_c': {'cpu': 60.7}}}
STREAM = {'state': 'UNAVAILABLE', 'received': 0}


def status(rt):
    return {'runtime': rt, 'configuration': 'configured', 'error': '', 'modes': [], 'streams': {k: dict(STREAM) for k in ('rgb', 'depth', 'ir', 'cloud')},
            'calibration': '', 'camera_info': {}, 'usb_verified': True, 'usb_note': '', 'depth_stats': None, 'dropped_messages': '', 'tf': '', 'detections': ''}


class Server:
    def __init__(self):
        self.started_at = None; self.posts = []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def out(self, code, body, ctype):
                self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                p = self.path.split('?')[0]
                if p.startswith('/api/vision3d/status'):
                    # Old state keeps being served for 3 s after Start (slow/in-flight replies), then the new worker appears.
                    t = None if srv.started_at is None else time.time() - srv.started_at
                    rt = OLD if t is None or t < 3 else NEW_CHECK if t < 5 else NEW_BLOCK
                    return self.out(200, json.dumps(status(rt)).encode(), 'application/json')
                f = V2 / p.replace('/v2/', '', 1).lstrip('/')
                if p == '/v2/vision3d': f = V2 / 'vision3d.html'
                if f.is_file(): return self.out(200, f.read_bytes(), 'text/css' if f.suffix == '.css' else 'application/javascript' if f.suffix == '.js' else 'text/html')
                self.out(404, b'', 'text/plain')
            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0); body = json.loads(self.rfile.read(n) or b'{}'); srv.posts.append(body)
                if body.get('action') == 'start': srv.started_at = time.time()
                self.out(202, json.dumps({'state': 'CHECKING'}).encode(), 'application/json')
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.httpd.server_address[1]


class StaleSummary(unittest.TestCase):
    def test_previous_session_is_never_shown_after_start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright not installed')
        srv = Server()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            pg.goto(srv.url + '/v2/vision3d'); pg.wait_for_timeout(1500)
            self.assertIn('Camera off', pg.inner_text('#vlTitle'))          # before Start: last session shown
            pg.click('#startViewer'); seen = []
            for _ in range(28):
                pg.wait_for_timeout(250); seen.append((pg.inner_text('#vlTitle'), pg.inner_text('#vlDriver')))
            b.close()
        srv.httpd.shutdown()
        titles = [t for t, _ in seen]
        first_new = next(i for i, t in enumerate(titles) if t == 'Stopped to protect ATLAS')
        self.assertTrue(all(t == 'Checking before start' for t in titles[:first_new]), titles)
        self.assertNotIn('Stopped safely', [d for _, d in seen[:first_new]])            # old driver state never reused
        self.assertEqual([x.get('action') for x in srv.posts], ['start'])


if __name__ == '__main__':
    unittest.main()
