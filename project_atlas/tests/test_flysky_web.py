import io
import json
import re
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas_flysky_core as C  # noqa: E402
import atlas_flysky_web as W   # noqa: E402


class FakeTransport:
    def __init__(self, pubs=1):
        self.pubs, self.started, self.stopped, self.on_message = pubs, False, False, None

    def start(self, on_message):
        self.started, self.on_message = True, on_message

    def publisher_count(self):
        return self.pubs

    def stop(self):
        self.stopped = True


class FakeHandler:
    def __init__(self, path, body=None, headers=None):
        self.path = path
        self.headers = Message()
        raw = json.dumps(body).encode() if body is not None and not isinstance(body, bytes) else (body or b'')
        for k, v in {'Content-Type': 'application/json', 'Content-Length': str(len(raw)), 'Host': '192.168.1.15:8088',
                     'Origin': 'http://192.168.1.15:8088', 'X-Atlas-Flysky': '1', **(headers or {})}.items():
            if v is not None:
                self.headers[k] = v
        self.rfile, self.wfile = io.BytesIO(raw), io.BytesIO()
        self.code, self.sent = None, {}

    def send_response(self, c):
        self.code = c

    def send_header(self, k, v):
        self.sent[k] = v

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def msg(**kw):
    return json.dumps({'proto': 'sbus', 'hex': C.encode_sbus([992] * 16, **kw).hex()})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.tr = FakeTransport()
        self.svc = W.FlyskyService(lambda: self.tr, Path(self.tmp.name), self.clock, lambda: 1.7e9 + self.clock.t, start_threads=False)

    def tearDown(self):
        self.tmp.cleanup()

    def feed(self, n=10, **kw):
        for _ in range(n):
            self.clock.t += 0.02
            self.svc._on_message(msg(**kw))

    def test_idle_means_no_subscription_until_first_request(self):
        self.assertIsNone(self.svc.transport); self.assertFalse(self.tr.started)
        self.svc.state(); self.assertTrue(self.tr.started)

    def test_no_publisher_is_signal_not_verified_with_exact_reason(self):
        self.tr.pubs = 0
        s = self.svc.state()
        self.assertEqual(s['link']['label'], 'SIGNAL NOT VERIFIED'); self.assertFalse(s['link']['verified'])
        self.assertIn('does not forward SBUS', s['link']['reason']); self.assertEqual(s['channels'], [])
        self.assertTrue(s['read_only']); self.assertEqual(s['topic'], '/atlas/rc/frames')

    def test_publisher_without_frames_is_still_not_connected(self):
        s = self.svc.state()
        self.assertEqual(s['link']['label'], 'SIGNAL NOT VERIFIED'); self.assertIn('no valid frame', s['link']['reason'])

    def test_live_frames_connect(self):
        self.svc.ensure_started(); self.feed(20)
        s = self.svc.state(); self.assertEqual(s['link']['label'], 'CONNECTED'); self.assertEqual(len(s['channels']), 16)

    def test_stale_then_lost(self):
        self.svc.ensure_started(); self.feed(5); self.clock.t += 1.0
        self.assertEqual(self.svc.state()['link']['state'], 'STALE'); self.clock.t += 4.0
        self.assertEqual(self.svc.state()['link']['state'], 'LOST')

    def test_garbage_messages_do_not_break_the_service(self):
        self.svc.ensure_started()
        for bad in ('not json', '{}', '[]', json.dumps({'proto': 'sbus', 'hex': 'zz'})):
            self.svc._on_message(bad)
        s = self.svc.state(); self.assertGreaterEqual(s['bad_source_messages'], 3); self.assertFalse(s['link']['verified'])

    def test_recording_saves_csv_and_retains_last_n(self):
        self.svc.ensure_started()
        r = self.svc.act({'action': 'session_start'}); self.feed(30)
        self.assertEqual(self.svc.state()['session']['id'], r['id'])
        out = self.svc.act({'action': 'session_stop'})
        self.assertTrue(out['file'].startswith('flysky_')); text = (Path(self.tmp.name) / out['file']).read_text()
        self.assertIn('ch1_raw', text.splitlines()[0]); self.assertGreater(len(text.splitlines()), 5)
        self.assertEqual(self.svc.csv_for(r['id']), text)
        self.assertEqual((Path(self.tmp.name) / out['file']).stat().st_mode & 0o777, 0o640)
        for _ in range(W.KEEP_FILES + 5):
            self.svc.act({'action': 'session_start'}); self.clock.t += 1; self.svc.wall = lambda: 1.7e9 + self.clock.t; self.svc.act({'action': 'session_stop'})
        self.assertLessEqual(len(list(Path(self.tmp.name).glob('flysky_*.csv'))), W.KEEP_FILES)

    def test_double_start_and_stop_without_session_refused(self):
        self.svc.act({'action': 'session_start'})
        with self.assertRaises(ValueError):
            self.svc.act({'action': 'session_start'})
        self.svc.act({'action': 'session_stop'})
        with self.assertRaises(ValueError):
            self.svc.act({'action': 'session_stop'})

    def test_only_allow_listed_actions_with_exact_fields(self):
        for bad in ({'action': 'drive'}, {'action': 'session_start', 'x': 1}, {'action': 'cmd_vel', 'linear': 1}, {}, {'action': 'estop_release'},
                    {'action': 'select_remote', 'source': 'flysky'}, {'action': 'reset_ranges', 'x': 1}):
            with self.assertRaises(ValueError):
                self.svc.act(bad)
        self.assertEqual(set(W.ACTIONS), {'session_start', 'session_stop', 'reset_ranges'})

    def test_service_stop_closes_and_saves_open_session(self):
        self.svc.ensure_started(); self.svc.act({'action': 'session_start'}); self.feed(5); self.svc.stop()
        self.assertTrue(self.tr.stopped); self.assertEqual(len(list(Path(self.tmp.name).glob('flysky_*.csv'))), 1)

    def test_idle_shutdown_rules(self):
        svc = W.FlyskyService(lambda: self.tr, Path(self.tmp.name), self.clock, start_threads=False)
        svc.ensure_started(); self.clock.t += W.IDLE_STOP_S + 1
        self.assertTrue(self.clock() - svc.touched > W.IDLE_STOP_S)     # the tick loop would stop here (no session open)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.svc = W.FlyskyService(lambda: FakeTransport(), Path(self.tmp.name), self.clock, lambda: 1.7e9 + self.clock.t, start_threads=False)

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, body, **kw):
        h = FakeHandler('/api/flysky/action', body, kw.get('headers'))
        self.assertTrue(W.serve(h, post=True, service=self.svc)); return h

    def test_state_and_csv_routes(self):
        h = FakeHandler('/api/flysky/state'); self.assertTrue(W.serve(h, service=self.svc)); self.assertEqual(h.code, 200)
        self.assertEqual(h.sent['Cache-Control'], 'no-store'); self.assertTrue(h.json()['read_only'])
        self.post({'action': 'session_start'}); h = FakeHandler('/api/flysky/session.csv'); W.serve(h, service=self.svc)
        self.assertEqual(h.code, 200); self.assertIn('text/csv', h.sent['Content-Type'])
        h = FakeHandler('/api/flysky/session.csv?id=000000000000'); W.serve(h, service=self.svc); self.assertEqual(h.code, 404)
        h = FakeHandler('/api/flysky/session.csv?id=../../etc/passwd'); W.serve(h, service=self.svc); self.assertEqual(h.code, 404)

    def test_post_security(self):
        self.assertEqual(self.post({'action': 'session_start'}, headers={'X-Atlas-Flysky': None}).code, 403)
        self.assertEqual(self.post({'action': 'session_start'}, headers={'Origin': 'http://evil.example'}).code, 403)
        self.assertEqual(self.post({'action': 'session_start'}, headers={'X-Atlas-Testlab': '1', 'X-Atlas-Flysky': '0'}).code, 403)
        self.assertEqual(self.post({'action': 'session_start'}, headers={'Content-Type': 'text/plain'}).code, 400)
        self.assertEqual(self.post(b'x' * 300).code, 400)
        self.assertEqual(self.post([1, 2]).code, 400)
        self.assertEqual(self.post({'action': 'drive'}).code, 400)
        self.assertEqual(self.post({'action': 'session_start'}).code, 200)

    def test_get_does_not_act_and_unknown_routes_404(self):
        h = FakeHandler('/api/flysky/action'); W.serve(h, service=self.svc); self.assertEqual(h.code, 404)
        h = FakeHandler('/api/flysky/nothing'); W.serve(h, post=True, service=self.svc); self.assertEqual(h.code, 404)
        self.assertFalse(W.serve(FakeHandler('/api/testlab/state'), service=self.svc))
        self.assertIsNone(self.svc.lab.session)


class NoActuation(unittest.TestCase):
    """Moving sticks must only change displayed numbers."""
    SRC = (SCRIPTS / 'atlas_flysky_web.py').read_text()

    def test_no_publishers_no_motion_types_no_serial_no_network(self):
        body = re.sub(r'"""[\s\S]*?"""', '', self.SRC)           # drop the module docstring (it names what is forbidden)
        for bad in ('create_publisher', 'geometry_msgs', 'Twist', 'import serial', 'serial.Serial', '/dev/tty', 'ttyUSB', 'subprocess', 'socket',
                    'urllib.request', 'requests', 'create_client', 'ActionClient', 'create_service', 'os.system'):
            self.assertNotIn(bad, body, bad)
        self.assertIsNone(re.search(r'(?<![a-z])e_stop|estop', body.lower()))
        self.assertEqual(body.count('create_subscription'), 1)
        self.assertIn("'/atlas/rc/frames'", body)

    def test_transport_creates_exactly_one_subscription_and_no_publisher(self):
        import types
        calls = {'sub': [], 'pub': 0}

        class Node:
            def create_subscription(self, t, topic, cb, depth): calls['sub'].append(topic)
            def create_publisher(self, *a, **k): calls['pub'] += 1
            def get_publishers_info_by_topic(self, t): return []
            def destroy_node(self): pass

        class Exec:
            def add_node(self, n): pass
            def spin(self): pass
            def shutdown(self): pass
        rclpy = types.ModuleType('rclpy'); rclpy.create_node = lambda name: Node()
        ex = types.ModuleType('rclpy.executors'); ex.SingleThreadedExecutor = Exec; rclpy.executors = ex
        std = types.ModuleType('std_msgs'); msgs = types.ModuleType('std_msgs.msg'); msgs.String = str; std.msg = msgs
        saved = {k: sys.modules.get(k) for k in ('rclpy', 'rclpy.executors', 'std_msgs', 'std_msgs.msg')}
        sys.modules.update({'rclpy': rclpy, 'rclpy.executors': ex, 'std_msgs': std, 'std_msgs.msg': msgs})
        try:
            t = W.RosTransport(); t.start(lambda d: None); t.stop()
        finally:
            for k, v in saved.items():
                sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        self.assertEqual(calls['sub'], ['/atlas/rc/frames']); self.assertEqual(calls['pub'], 0)

    def test_stick_movement_changes_only_state_and_publishes_nothing(self):
        tr = FakeTransport(); svc = W.FlyskyService(lambda: tr, Path(tempfile.mkdtemp()), Clock(), start_threads=False)
        svc.ensure_started(); before = dir(tr)
        for k in range(100):
            svc._on_message(json.dumps({'proto': 'sbus', 'hex': C.encode_sbus([172 + k * 16] * 16).hex()}))
        self.assertEqual(dir(tr), before)             # the transport object grew no publish/command surface
        self.assertFalse(hasattr(tr, 'publish')); self.assertFalse(hasattr(svc, 'publish'))

    def test_does_not_import_other_atlas_control_modules(self):
        imports = re.findall(r'^\s*(?:import|from)\s+(\S+)', self.SRC, re.M)
        atlas = sorted({i.split('.')[0] for i in imports if i.startswith('atlas_')})
        self.assertEqual(atlas, ['atlas_flysky_core', 'atlas_wifi_web'])       # wifi_web only for its same_origin() check


if __name__ == '__main__':
    unittest.main()
