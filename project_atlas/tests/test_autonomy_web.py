import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.modules.setdefault('atlas_wifi_web', types.SimpleNamespace(same_origin=lambda headers: True))
import atlas_autonomy_web as web


class Headers(dict):
    def get_content_type(self):
        return self.get('Content-Type', '')


class Handler:
    def __init__(self, path, body=None):
        raw = json.dumps(body).encode() if body is not None else b''
        self.path = path
        self.headers = Headers({'Content-Length': str(len(raw)), 'Content-Type': 'application/json'})
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.client_address = ('127.0.0.1', 1)
        self.code = None

    def send_response(self, code): self.code = code
    def send_header(self, *a): pass
    def end_headers(self): pass
    def send_error(self, code): self.code = code

    def json(self): return json.loads(self.wfile.getvalue() or b'{}')


class Pub:
    def __init__(self): self.sent = []
    def publish(self, msg): self.sent.append(msg.data)


class Log:
    def write(self, *a, **k): pass


class Pins:
    def verify(self, pin): return pin == '1234'


class Lockout:
    def __init__(self): self.fails = 0
    def remaining(self): return 0
    def fail(self): self.fails += 1
    def success(self): pass


def ros(policy):
    r = types.SimpleNamespace(estop_log=Log(), reset_pins=Pins(), reset_lockout=Lockout(),
                              place_pubs={k: Pub() for k in ('save', 'go', 'delete', 'save_at')}, autonomy_clients={})
    r._item = lambda key: {'value': json.dumps(policy), 'ts': time.time()} if policy is not None else None
    return r


class AutonomyWebTests(unittest.TestCase):
    def setUp(self):
        try:
            import std_msgs  # noqa: F401
        except ImportError:
            m = types.ModuleType('std_msgs'); m.msg = types.SimpleNamespace(String=lambda data: types.SimpleNamespace(data=data))
            sys.modules['std_msgs'] = m; sys.modules['std_msgs.msg'] = m.msg

    def test_names_are_validated(self):
        self.assertEqual(web.clean_name('  Kitchen   Door '), 'kitchen door')
        for bad in ('', 'a' * 25, 'x;rm -rf', '../etc'):
            with self.assertRaises(ValueError):
                web.clean_name(bad)

    def test_go_refused_when_off_latched_or_stale(self):
        for pol in (None, {'autonomy': {'armed': False}, 'stop_latched': False},
                    {'autonomy': {'armed': True}, 'stop_latched': True}):
            r = ros(pol); h = Handler('/api/places', {'action': 'go', 'name': 'hall'})
            web.serve(h, r, post=True)
            self.assertEqual(h.code, 409, pol)
            self.assertEqual(r.place_pubs['go'].sent, [])

    def test_go_allowed_only_when_on_and_released(self):
        r = ros({'autonomy': {'armed': True}, 'stop_latched': False})
        h = Handler('/api/places', {'action': 'go', 'name': 'Hall'})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 202)
        self.assertEqual(r.place_pubs['go'].sent, ['hall'])

    def test_save_and_delete_publish_clean_names(self):
        r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
        for action in ('save', 'delete'):
            h = Handler('/api/places', {'action': action, 'name': 'Kitchen'})
            web.serve(h, r, post=True)
            self.assertEqual(h.code, 202)
            self.assertEqual(r.place_pubs[action].sent, ['kitchen'])

    def test_save_at_publishes_point_and_rejects_garbage(self):
        r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
        h = Handler('/api/places', {'action': 'save_at', 'name': 'Sofa', 'x': 1.25, 'y': -0.5})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 202)
        self.assertEqual(json.loads(r.place_pubs['save_at'].sent[0]), {'name': 'sofa', 'x': 1.25, 'y': -0.5})
        for bad in ({'x': 'a', 'y': 1}, {'x': 1e9, 'y': 0}, {'y': 1}):
            h = Handler('/api/places', dict(bad, action='save_at', name='x'))
            web.serve(h, r, post=True)
            self.assertEqual(h.code, 400, bad)

    def test_on_needs_pin(self):
        r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
        h = Handler('/api/autonomy', {'action': 'on', 'pin': '0000'})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 403)
        self.assertEqual(r.reset_lockout.fails, 1)

    def test_on_with_pin_but_no_mux_is_refused(self):
        r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
        h = Handler('/api/autonomy', {'action': 'on', 'pin': '1234'})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 409)
        self.assertFalse(h.json()['ok'])

    def test_places_list_reads_file(self):
        f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump({'map_id': 'm1', 'a': {'frame_id': 'map', 'x': 1, 'y': 2, 'map_id': 'm1'},
                   'b': {'frame_id': 'map', 'x': 3, 'y': 4, 'map_id': 'old'}}, f); f.close()
        old, oldid = web.PLACES_FILE, web.accepted_map_id
        web.PLACES_FILE = Path(f.name); web.accepted_map_id = lambda: 'm1'
        try:
            plist, mid = web.places()
        finally:
            web.PLACES_FILE, web.accepted_map_id = old, oldid
        self.assertEqual(mid, 'm1')
        self.assertEqual([(p['name'], p['current_map']) for p in plist], [('a', True), ('b', False)])

    def test_unrelated_paths_not_served(self):
        self.assertFalse(web.serve(Handler('/api/status'), ros(None)))


if __name__ == '__main__':
    unittest.main()
