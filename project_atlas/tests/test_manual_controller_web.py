"""Stage 29 dashboard: controller selection endpoint, status-web hooks and the FlySky Driving page."""
import io
import json
import re
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'tools/deploy/stage29_flysky_drive'))
import atlas_manual_controller_web as W     # noqa: E402
import insert_status_web_hooks as hooks     # noqa: E402
import atlas_web_v2                         # noqa: E402
try:
    from playwright.sync_api import sync_playwright
    HAVE = True
except Exception:       # pragma: no cover
    HAVE = False


class FakeFuture:
    def __init__(self, ok, msg): self.r = NS(success=ok, message=msg)
    def done(self): return True
    def result(self): return self.r
    def cancel(self): pass


class FakeClient:
    srv_type = NS(Request=lambda: object())

    def __init__(self, ros, target): self.ros, self.target = ros, target
    def service_is_ready(self): return self.ros.service_up
    def call_async(self, req):
        self.ros.calls.append(self.target)
        ok = self.ros.policy['stop_latched'] is True
        if ok:
            self.ros.policy['manual_controller'] = self.target
        return FakeFuture(ok, 'Manual controller is %s.' % self.target if ok else 'Latch the E-STOP before changing controller')


class FakeROS:
    def __init__(self, latched=True, enabled=True, supported=True, drive=None):
        self.ready, self.service_up, self.calls, self.log = True, True, [], []
        self.policy = {'stop_latched': latched, 'stop_reason': 'REMOTE STOP: B pressed', 'source': 'STOPPED'}
        if supported:
            self.policy.update(manual_controller='XBOX', flysky_drive_enabled=enabled)
        self.drive = drive
        self.manual_controller_clients = {t: FakeClient(self, t) for t in ('XBOX', 'FLYSKY')}
        self.estop_log = NS(write=lambda event, **kw: self.log.append((event, kw)))

    def _item(self, key):
        if key == 'control_policy':
            return {'value': json.dumps(self.policy), 'ts': time.time()}
        if key == 'flysky_drive' and self.drive is not None:
            return {'value': json.dumps(self.drive), 'ts': time.time()}
        return None


class Headers(dict):
    def get_content_type(self): return self.get('Content-Type', '')


def call(ros, body=None, post=True, headers=None, path=W.ROUTE):
    raw = json.dumps(body).encode() if isinstance(body, dict) else (body or b'')
    h = Headers({'Origin': 'http://192.168.1.16:8088', 'Host': '192.168.1.16:8088', 'X-Atlas-Controller': '1',
                 'Content-Type': 'application/json', 'Content-Length': str(len(raw))})
    h.update(headers or {})
    out = io.BytesIO(); res = {}
    hd = NS(path=path, headers=h, rfile=io.BytesIO(raw), wfile=out, client_address=('192.168.1.20', 1),
            send_response=lambda c: res.update(code=c), send_header=lambda *a: None, end_headers=lambda: None)
    handled = W.serve(hd, ros, post=post)
    return handled, res.get('code'), (json.loads(out.getvalue()) if out.getvalue() else None)


class Endpoint(unittest.TestCase):
    def test_other_routes_are_not_handled(self):
        self.assertFalse(call(FakeROS(), path='/api/estop/reset')[0])

    def test_get_view(self):
        _, code, v = call(FakeROS(), post=False)
        self.assertEqual(code, 200); self.assertEqual(v['policy']['manual_controller'], 'XBOX')
        self.assertEqual(v['can_select'], {'XBOX': False, 'FLYSKY': True}); self.assertFalse(v['drive']['running'])

    def test_released_estop_blocks_both(self):
        v = W.view(FakeROS(latched=False))
        self.assertEqual(v['can_select'], {'XBOX': False, 'FLYSKY': False}); self.assertIn('latch', v['blocked_reason'])

    def test_unpatched_mux_is_xbox_only(self):
        v = W.view(FakeROS(supported=False))
        self.assertFalse(v['policy']['selection_supported']); self.assertFalse(any(v['can_select'].values()))

    def test_gate_off_blocks_flysky(self):
        self.assertFalse(W.view(FakeROS(enabled=False))['can_select']['FLYSKY'])

    def test_stale_policy_blocks(self):
        ros = FakeROS(); ros._item = lambda k: {'value': json.dumps(ros.policy), 'ts': time.time() - 5} if k == 'control_policy' else None
        v = W.view(ros); self.assertFalse(v['policy']['fresh']); self.assertFalse(any(v['can_select'].values()))

    def test_post_selects_when_latched_and_logs(self):
        ros = FakeROS(); _, code, j = call(ros, {'target': 'FLYSKY'})
        self.assertEqual((code, j['ok']), (200, True)); self.assertEqual(ros.calls, ['FLYSKY'])
        self.assertEqual(ros.log[-1][0], 'controller_select')

    def test_post_refused_before_calling_mux_when_released(self):
        ros = FakeROS(latched=False); _, code, j = call(ros, {'target': 'FLYSKY'})
        self.assertEqual(code, 409); self.assertEqual(ros.calls, [])

    def test_post_security(self):
        ros = FakeROS()
        self.assertEqual(call(ros, {'target': 'FLYSKY'}, headers={'X-Atlas-Controller': ''})[1], 403)
        self.assertEqual(call(ros, {'target': 'FLYSKY'}, headers={'Origin': 'http://evil.example'})[1], 403)
        for bad in ({'target': 'PS5'}, {'target': 'FLYSKY', 'reset': True}, {'target': 'FLYSKY', 'pin': '1234'}, {}):
            self.assertEqual(call(ros, bad)[1], 400, bad)
        self.assertEqual(call(ros, b'x' * 200, headers={'Content-Length': '200'})[1], 400)
        self.assertEqual(ros.calls, [])

    def test_service_unavailable(self):
        ros = FakeROS(); ros.service_up = False
        _, code, j = call(ros, {'target': 'FLYSKY'}); self.assertEqual(code, 409); self.assertIn('unavailable', j['message'])

    def test_module_cannot_drive_or_release(self):
        code = (ROOT / 'scripts/atlas_manual_controller_web.py').read_text()
        for bad in ('create_publisher', 'Twist', 'cmd_vel', '/api/estop/reset', 'remote_stop/reset', 'create_subscription', 'subprocess'):
            self.assertNotIn(bad, code, bad)


class Hooks(unittest.TestCase):
    BASE = ROOT / 'tools/deploy/stage29_flysky_drive/baseline/atlas_status_web.py.live-4ab16214'

    def test_hooks_are_additive_and_compile(self):
        old = self.BASE.read_text(); new = hooks.apply(old); compile(new, 'w', 'exec')
        o, n = old.splitlines(), new.splitlines()
        self.assertEqual([l for l in o if l not in n], [])
        self.assertEqual(len(n) - len(o), 9)
        with self.assertRaises(SystemExit):
            hooks.apply(new)

    def test_page_registered(self):
        self.assertEqual(atlas_web_v2.PAGES['flysky-drive'], 'flysky-drive.html')
        self.assertEqual(atlas_web_v2.PAGES['flysky-testlab'], 'flysky-testlab.html')


class PageStatic(unittest.TestCase):
    def test_page_js_only_selects_a_remote(self):
        js = (ROOT / 'web/v2/flysky-drive.js').read_text(); code = re.sub(r'/\*[\s\S]*?\*/', '', js)
        self.assertEqual(sorted(set(re.findall(r"fetch\('([^']+)'", code))), ['/api/manual_controller'])
        self.assertEqual(code.count("method: 'POST'"), 1)
        for bad in ('/api/estop', 'cmd_vel', 'innerHTML', 'eval(', 'WebSocket', 'XMLHttpRequest', 'pin', 'reset'):
            self.assertNotIn(bad, code, bad)
        html = (ROOT / 'web/v2/flysky-drive.html').read_text()
        self.assertIn('id="v2Estop"', html); self.assertIsNone(re.search(r'\son[a-z]+=', html))
        self.assertEqual(re.findall(r'(?:src|href)="(https?:)?//', html), [])


@unittest.skipUnless(HAVE, 'playwright not installed')
class PageRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ros = FakeROS()
        ros = cls.ros

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                if W.serve(self, ros):
                    return
                hit = atlas_web_v2.resolve(self.path) if atlas_web_v2.handles(self.path) else None
                if self.path in ('/v2/estop.js',) or hit is None:
                    self.send_response(200); self.send_header('Content-Type', 'application/javascript'); self.send_header('Content-Length', '0'); self.end_headers(); return
                f, mime = hit; body = f.read_bytes()
                self.send_response(200); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                self.headers.get_content_type = lambda: self.headers.get('Content-Type', '')
                if not W.serve(self, ros, post=True):
                    self.send_response(404); self.end_headers()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), H); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        try:
            cls.pw = sync_playwright().start(); cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.srv.shutdown(); raise unittest.SkipTest('chromium unavailable: %s' % exc)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.srv.shutdown()

    def open(self, w=1280, h=900):
        pg = self.browser.new_page(viewport={'width': w, 'height': h}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto('http://127.0.0.1:%d/v2/flysky-drive' % self.port); pg.wait_for_timeout(900)
        return pg, errs

    def test_latched_allows_flysky_and_click_switches(self):
        self.ros.policy.update(stop_latched=True, manual_controller='XBOX'); self.ros.drive = None
        pg, errs = self.open()
        self.assertTrue(pg.is_disabled('#useXbox')); self.assertFalse(pg.is_disabled('#useFlysky'))
        self.assertIn('Drive node not running', pg.inner_text('#chipState'))
        pg.click('#useFlysky'); pg.wait_for_timeout(1200)
        self.assertIn('Manual controller is FLYSKY', pg.inner_text('#selNote'))
        self.assertIn('FlySky', pg.inner_text('#chipCtl')); self.assertEqual(errs, []); pg.close()

    def test_released_blocks_and_armed_status_renders_on_phone(self):
        self.ros.policy.update(stop_latched=False, manual_controller='FLYSKY')
        self.ros.drive = {'state': 'ARMED', 'reason': 'armed', 'armed': True, 'command': [0.1, -0.2], 'frame_age_s': 0.05,
                          'inputs': {'arm': 'ON', 'stop': 'RUN', 'throttle': 0.6, 'steering': -0.3, 'speed_scale': 0.33,
                                     'failsafe': False, 'frame_lost': False},
                          'config': {'reviewed_by_owner': True, 'throttle': {'channel': 2, 'reversed': False, 'deadband': 0.08},
                                     'steering': {'channel': 4, 'reversed': True, 'deadband': 0.08}, 'arm_channel': 5,
                                     'stop_channel': 6, 'speed_mode_channel': 7, 'max_linear_mps': 0.15, 'max_angular_radps': 0.6,
                                     'hard_max_linear_mps': 0.25, 'hard_max_angular_radps': 0.8, 'errors': []}}
        pg, errs = self.open(390, 844)
        self.assertTrue(pg.is_disabled('#useXbox')); self.assertTrue(pg.is_disabled('#useFlysky'))
        self.assertIn('latch the E-STOP first', pg.inner_text('#selNote'))
        self.assertIn('FlySky armed', pg.inner_text('#banner')); self.assertIn('CH2', pg.inner_text('#cfg'))
        self.assertFalse(pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'))
        self.assertEqual(errs, []); pg.close()


if __name__ == '__main__':
    unittest.main()
