import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
# 2026-11-19: stub atlas_wifi_web only for this import; never leave it in sys.modules (it made later
# tests' origin checks always pass: test_flysky_web / test_testlab_web failed when run in one process).
_saved_wifi = sys.modules.get('atlas_wifi_web')
sys.modules['atlas_wifi_web'] = types.SimpleNamespace(same_origin=lambda headers: True)
import atlas_autonomy_web as web
if _saved_wifi is None:
    del sys.modules['atlas_wifi_web']
else:
    sys.modules['atlas_wifi_web'] = _saved_wifi


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
                              place_pubs={k: Pub() for k in ('save', 'go', 'delete', 'save_at', 'go_at')}, autonomy_clients={})
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

    def test_go_at_needs_on_and_released(self):
        r = ros({'autonomy': {'armed': False}, 'stop_latched': False})
        h = Handler('/api/places', {'action': 'go_at', 'x': 1.0, 'y': 2.0})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 409); self.assertEqual(r.place_pubs['go_at'].sent, [])
        r = ros({'autonomy': {'armed': True}, 'stop_latched': False})
        h = Handler('/api/places', {'action': 'go_at', 'x': 1.0, 'y': 2.0})
        web.serve(h, r, post=True)
        self.assertEqual(h.code, 202)
        self.assertEqual(json.loads(r.place_pubs['go_at'].sent[0]), {'x': 1.0, 'y': 2.0})

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

    def test_speedcheck_refusals(self):
        import tempfile as _t
        tool = Path(_t.mkdtemp()) / 'speed_loop_ground_check.py'
        old = web.GROUND_CHECK
        try:
            web.GROUND_CHECK = tool
            r = ros({'autonomy': {'armed': False}, 'stop_latched': False})
            self.assertEqual(web.start_speedcheck(r, 0.12, '1234')[0], 400)          # only 0.10 / 0.15
            self.assertEqual(web.start_speedcheck(r, 0.10, '1234')[0], 409)          # tool missing
            tool.write_text('# tool')
            self.assertEqual(web.start_speedcheck(r, 0.10, '0000')[0], 403)          # wrong PIN
            r = ros({'autonomy': {'armed': True}, 'stop_latched': False})
            self.assertIn('Manual', web.start_speedcheck(r, 0.10, '1234')[1])
            r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
            self.assertIn('E-STOP', web.start_speedcheck(r, 0.10, '1234')[1])
        finally:
            web.GROUND_CHECK = old

    def test_turncheck_refusals_and_stage1_lock(self):
        import tempfile as _t
        import atlas_master_plan
        tool = Path(_t.mkdtemp()) / 'turn_ground_check.py'
        old, old_ev = web.TURN_CHECK, atlas_master_plan.stage1_evidence
        try:
            web.TURN_CHECK = tool
            r = ros({'autonomy': {'armed': False}, 'stop_latched': False})
            self.assertEqual(web.start_turncheck(r, '1234')[0], 409)                  # tool missing
            tool.write_text('# tool')
            atlas_master_plan.stage1_evidence = lambda *a, **k: None
            code, msg = web.start_turncheck(r, '1234')
            self.assertEqual(code, 409); self.assertIn('Stage 1', msg)              # locked until stage 1 PASS
            atlas_master_plan.stage1_evidence = lambda *a, **k: {'detail': 'ok', 'when': 'w', 'file': 'f'}
            self.assertEqual(web.start_turncheck(r, '0000')[0], 403)                  # wrong PIN
            old_plan = atlas_master_plan.evaluate
            atlas_master_plan.evaluate = lambda *a, **k: {'gate_open': False}
            code, msg = web.start_turncheck(r, '1234', workload=True)
            self.assertEqual(code, 409); self.assertIn('Stage 4 is locked', msg)     # part B needs the gate
            atlas_master_plan.evaluate = old_plan
            r = ros({'autonomy': {'armed': True}, 'stop_latched': False})
            self.assertIn('Manual', web.start_turncheck(r, '1234')[1])
            r = ros({'autonomy': {'armed': False}, 'stop_latched': True})
            self.assertIn('E-STOP', web.start_turncheck(r, '1234')[1])
        finally:
            web.TURN_CHECK, atlas_master_plan.stage1_evidence = old, old_ev

    def test_imucheck_locked_until_gate_open(self):
        import tempfile as _t
        import atlas_master_plan
        tool = Path(_t.mkdtemp()) / 'imu_ekf_tf_parked_check.py'
        old, old_ev = web.IMU_CHECK, atlas_master_plan.evaluate
        try:
            web.IMU_CHECK = tool
            r = ros({'autonomy': {'armed': False}, 'stop_latched': False})
            self.assertEqual(web.start_imucheck(r)[0], 409)                           # tool missing
            tool.write_text('# tool')
            atlas_master_plan.evaluate = lambda *a, **k: {'gate_open': False}
            code, msg = web.start_imucheck(r)
            self.assertEqual(code, 409); self.assertIn('locked', msg)
            atlas_master_plan.evaluate = lambda *a, **k: {'gate_open': True}
            r = ros({'autonomy': {'armed': True}, 'stop_latched': False})
            self.assertIn('Manual', web.start_imucheck(r)[1])
        finally:
            web.IMU_CHECK, atlas_master_plan.evaluate = old, old_ev

    def test_unrelated_paths_not_served(self):
        self.assertFalse(web.serve(Handler('/api/status'), ros(None)))


if __name__ == '__main__':
    unittest.main()
