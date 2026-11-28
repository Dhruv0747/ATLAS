import io
import json
import os
from email.message import Message
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import atlas_testlab_core as T  # noqa: E402
import atlas_testlab_web as W  # noqa: E402
from test_testlab_core import FakeOwner, make_frame  # noqa: E402

C = T.CIRCUMFERENCE_M
CHECK = {k: True for k in W.CHECKLIST_KEYS}


class FakeTransport:
    def __init__(self, owner):
        self.owner, self.published, self.started, self.stopped = owner, [], False, False

    def start(self, on_update, on_health, on_status):
        self.started = True

    def publish_lifted_request(self, msg):
        self.published.append(dict(msg))
        self.owner.request(msg)

    def subscriber_count(self):
        return 1

    def stop(self):
        self.stopped = True


class FakeHandler:
    def __init__(self, path, body=None, headers=None):
        self.path = path
        self.headers = Message()
        raw = json.dumps(body).encode() if body is not None and not isinstance(body, bytes) else (body or b'')
        for k, v in {'Content-Type': 'application/json', 'Content-Length': str(len(raw)),
                     'Host': '192.168.1.15:8088', 'Origin': 'http://192.168.1.15:8088',
                     'X-Atlas-Testlab': '1', **(headers or {})}.items():
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


class Rig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.owner = FakeOwner()
        self.tr = FakeTransport(self.owner)
        self.svc = W.TestLabService(lambda: self.tr, Path(self.tmp.name), clock=lambda: self.owner.now,
                                    wall=lambda: 1.8e9 + self.owner.now, start_threads=False)
        self.dist = [0.0] * 4

    def feed(self, dist=None, n=1, dt=0.05):
        for _ in range(n):
            self.owner.advance(dt)
            if dist:
                self.dist = [self.dist[i] + dist[i] * C * dt for i in range(4)]
            raw = [int(self.dist[i] / C * 2200) * (1, -1, 1, -1)[i] for i in range(4)]
            self.svc._on_update(json.dumps({'sequence': int(self.owner.now * 20), 'raw_counts': raw,
                                            'wheel_distances_m': self.dist, 'packet_fresh': True, 'packet_age_s': 0.02,
                                            'accepted_channels': [1, 2, 3, 4], 'rejected_channels': []}))
            self.svc._on_status(json.dumps(self.owner.status()))
            self.svc._tick_run()

    def post(self, body, **kw):
        h = FakeHandler('/api/testlab/action', body, kw.get('headers'))
        self.assertTrue(W.serve(h, post=True, service=self.svc))
        return h

    def get(self, path):
        h = FakeHandler(path)
        self.assertTrue(W.serve(h, service=self.svc))
        return h

    def pulse_body(self, **kw):
        b = {'action': 'pulse_start', 'wheel': 2, 'direction': 'forward', 'pwm': 30, 'duration_s': 0.3,
             'confirm': T.CONFIRMATION_PHRASE, 'checklist': dict(CHECK)}
        b.update(kw)
        return b


class ReadOnlyBehaviour(Rig):
    def test_state_without_any_owner_is_read_only_and_closed(self):
        self.feed([1, 1, 1, 1], n=40)
        self.owner.raw_enabled = False
        self.feed(n=2)
        h = self.get('/api/testlab/state')
        d = h.json()
        self.assertEqual(h.code, 200)
        self.assertFalse(d['gate']['entry_ok'])
        self.assertEqual(self.tr.published, [])
        self.assertEqual([c['channel'] for c in d['view']['channels']], [1, 2, 3, 4])
        self.assertIn('graph', d)
        self.assertEqual(self.get('/api/testlab/state?history=0').json().get('graph'), None)

    def test_gate_closed_when_status_never_arrives(self):
        self.svc.ensure_started()
        d = self.svc.state()
        self.assertFalse(d['gate']['entry_ok'])
        self.assertIsNone(d['owner'])

    def test_hand_test_full_flow_publishes_nothing(self):
        self.feed(n=5)
        self.assertEqual(self.post({'action': 'session_start', 'mode': 'hand'}).code, 200)
        for w in (1, 2, 3, 4):
            for dr in ('forward', 'reverse'):
                self.assertEqual(self.post({'action': 'hand_begin', 'wheel': w, 'direction': dr}).code, 200)
                d = [0.0] * 4
                d[w - 1] = (1 if dr == 'forward' else -1) * 1.0 / 2.0           # 1 turn/s for 2 s at dt .05
                self.feed(d, n=40)
                r = self.post({'action': 'hand_finish'})
                self.assertEqual(r.code, 200)
                self.assertEqual(r.json()['result']['status'], 'PASS', (w, dr, r.json()))
        st = self.get('/api/testlab/state').json()
        self.assertTrue(all(v['verdict'] == 'PASS' for v in st['hand']['summary'].values()))
        stop = self.post({'action': 'session_stop'}).json()
        self.assertTrue(stop['file'].endswith('.csv'))
        self.assertEqual(self.tr.published, [])
        self.assertEqual(self.owner.requests, [])

    def test_hand_step_refused_when_data_stale(self):
        self.feed(n=3)
        self.owner.now += 2.0
        self.assertEqual(self.post({'action': 'hand_begin', 'wheel': 1, 'direction': 'forward'}).code, 403)

    def test_csv_download_and_traversal(self):
        self.feed(n=5)
        sid = self.post({'action': 'session_start', 'mode': 'observe'}).json()['session']
        self.feed([1, 1, 1, 1], n=10)
        h = self.get('/api/testlab/session.csv?id=' + sid)
        self.assertEqual(h.code, 200)
        self.assertIn('text/csv', h.sent['Content-Type'])
        lines = h.wfile.getvalue().decode().splitlines()
        self.assertEqual(lines[0].split(',')[:3], ['iso_time_utc', 'monotonic_s', 'session_id'])
        self.assertGreaterEqual(len(lines), 41)
        self.post({'action': 'session_stop'})
        self.assertEqual(self.get('/api/testlab/session.csv?id=' + sid).code, 200)         # saved copy / last session
        for bad in ('../../etc/passwd', '..%2F..%2Fetc%2Fpasswd', 'zzzzzzzzzzzz', ''):
            h = self.get('/api/testlab/session.csv?id=' + bad)
            self.assertIn(h.code, (200, 404))
            self.assertNotIn(b'root:', h.wfile.getvalue())


class PostHardening(Rig):
    def test_header_origin_size_type(self):
        body = {'action': 'session_stop'}
        self.assertEqual(self.post(body, headers={'X-Atlas-Testlab': None}).code, 403)
        self.assertEqual(self.post(body, headers={'Origin': 'http://evil.example'}).code, 403)
        self.assertEqual(self.post(body, headers={'Origin': None}).code, 403)
        self.assertEqual(self.post(body, headers={'Content-Type': 'text/plain'}).code, 400)
        self.assertEqual(self.post(b'{' + b' ' * 600 + b'}').code, 400)
        self.assertEqual(self.post(b'').code, 400)
        self.assertEqual(self.post([1, 2]).code, 400)
        self.assertEqual(self.post(b'not json').code, 400)
        self.assertEqual(self.post(body).code, 200)

    def test_unknown_actions_and_extra_fields_rejected(self):
        for bad in ({'action': 'motor'}, {'action': 'set_pwm', 'pwm': 10}, {'action': 'cmd_vel'}, {'action': 'pulse_start'},
                    {'action': 'session_stop', 'extra': 1}, {'action': 'hand_begin', 'wheel': 1}, {}, {'a': 1},
                    self.pulse_body(op='arm'), self.pulse_body(mode='pid_single')):
            self.assertEqual(self.post(bad).code, 400, bad)
        self.assertEqual(self.tr.published, [])

    def test_get_post_route_split(self):
        h = FakeHandler('/api/testlab/state', {'action': 'session_stop'})
        self.assertTrue(W.serve(h, post=True, service=self.svc))
        self.assertEqual(h.code, 404)
        self.assertFalse(W.serve(FakeHandler('/api/other'), service=self.svc))


class PulseGating(Rig):
    def ready(self):
        self.feed(n=10)

    def test_refusals_publish_nothing(self):
        self.ready()
        cases = [self.pulse_body(confirm='yes'), self.pulse_body(confirm=''),
                 self.pulse_body(checklist={**CHECK, 'wheels_lifted': False}),
                 self.pulse_body(checklist={k: 'true' for k in CHECK}), self.pulse_body(checklist={}),
                 self.pulse_body(checklist={**CHECK, 'extra': True})]
        for b in cases:
            self.assertEqual(self.post(b).code, 403, b)
        for b in (self.pulse_body(wheel=0), self.pulse_body(wheel=5), self.pulse_body(pwm=51), self.pulse_body(pwm=0),
                  self.pulse_body(pwm=-5), self.pulse_body(duration_s=0.1), self.pulse_body(duration_s=0.6),
                  self.pulse_body(direction='left'), self.pulse_body(wheel='2'), self.pulse_body(pwm=30.5)):
            self.assertEqual(self.post(b).code, 400, b)
        self.assertEqual(self.tr.published, [])
        self.assertIsNone(self.svc.run)

    def test_each_owner_gate_blocks_start(self):
        self.ready()
        for attr, val in (('raw_enabled', False), ('cut_ready', False), ('entry_problem', 'wheels_not_stationary'),
                          ('entry_stable', 1.0), ('stop_latched', False), ('remote_b', True)):
            fresh = FakeOwner()
            old = getattr(self.owner, attr)
            setattr(self.owner, attr, val)
            self.feed(n=2)
            h = self.post(self.pulse_body())
            self.assertEqual(h.code, 403, attr)
            self.assertEqual(self.tr.published, [], attr)
            setattr(self.owner, attr, old)
            self.feed(n=2)

    def test_stale_encoder_blocks_start(self):
        self.ready()
        self.owner.now += 1.0
        self.svc._on_status(json.dumps(self.owner.status()))
        self.assertEqual(self.post(self.pulse_body()).code, 403)
        self.assertEqual(self.tr.published, [])

    def test_stale_owner_status_blocks_start(self):
        self.ready()
        self.owner.now += 3.0
        self.feed(n=1)
        self.svc.status_at = self.owner.now - 3.0
        self.assertEqual(self.post(self.pulse_body()).code, 403)

    def test_open_hand_step_blocks_pulse(self):
        self.ready()
        self.post({'action': 'hand_begin', 'wheel': 1, 'direction': 'forward'})
        self.assertEqual(self.post(self.pulse_body()).code, 403)

    def test_full_supervised_pulse_run_and_csv(self):
        self.ready()
        h = self.post(self.pulse_body(wheel=3, direction='reverse', pwm=20, duration_s=0.25))
        self.assertEqual(h.code, 200, h.json())
        self.assertEqual(self.post(self.pulse_body()).code, 403, 'second run while active must be refused')
        for _ in range(80):
            self.feed(n=1)
            if self.svc.run.phase == 'WAIT_RELEASE':
                break
        self.assertEqual(self.svc.run.phase, 'WAIT_RELEASE')
        self.assertEqual([r for r in self.tr.published if r['op'] == 'pulse'], [])
        self.assertTrue(self.get('/api/testlab/state').json()['run']['needs_operator'])
        tok = Path(self.tmp.name) / 'lifted_session.json'
        self.assertTrue(tok.exists())
        self.assertEqual(oct(tok.stat().st_mode & 0o777), '0o600')
        self.owner.stop_latched = False               # operator action
        for _ in range(200):
            self.feed(n=1)
            if self.svc.run.phase == 'WAIT_RELATCH':
                break
        self.owner.stop_latched = True                # operator action
        for _ in range(100):
            self.feed(n=1)
            if self.svc.run.done:
                break
        self.assertEqual(self.svc.run.phase, 'DONE', self.svc.run.error)
        pulses = [r for r in self.tr.published if r['op'] == 'pulse']
        self.assertEqual(len(pulses), 1)
        self.assertEqual((pulses[0]['wheel'], pulses[0]['pwm'], pulses[0]['mode']), (3, -20, 'raw_pulse'))
        self.assertFalse(tok.exists(), 'session token removed after clean exit')
        self.feed(n=60)
        files = list(Path(self.tmp.name).glob('testlab_*_pulse_*.csv'))
        self.assertEqual(len(files), 1)
        txt = files[0].read_text()
        self.assertIn('pulse_requested', txt)
        self.assertIn('request_pulse', txt)
        self.assertIn('pulse_run_done', txt)
        self.assertIn('M3 front-left', txt)
        st = self.get('/api/testlab/state').json()
        self.assertEqual(st['pulse_results'][-1]['result'], 'MATCH')
        self.assertEqual(self.owner.last_pwm, (0, 0, 0, 0))
        self.assertEqual(self.post(self.pulse_body()).code, 403, 'cool-down after a run')

    def test_stop_button_cancels_mid_run(self):
        self.ready()
        self.assertEqual(self.post(self.pulse_body()).code, 200)
        for _ in range(60):
            self.feed(n=1)
            if self.svc.run.phase == 'WAIT_RELEASE':
                break
        self.owner.stop_latched = False
        self.feed(n=3)
        out = self.post({'action': 'pulse_cancel'}).json()
        self.assertTrue(out['cancelled'])
        self.feed(n=3)
        self.assertEqual(self.owner.last_pwm, (0, 0, 0, 0))
        self.assertNotEqual(self.owner.core.state.value, 'PULSE')
        self.assertEqual(self.post({'action': 'pulse_cancel'}).json()['cancelled'], False) if self.svc.run.done else None

    def test_transport_failure_during_run_fails_safe(self):
        self.ready()
        self.assertEqual(self.post(self.pulse_body()).code, 200)
        self.feed(n=3)
        self.assertEqual(self.svc.run.phase in ('WAIT_LOCKED', 'WAIT_RELEASE'), True)
        self.tr.publish_lifted_request = lambda msg: (_ for _ in ()).throw(RuntimeError('dds down'))
        self.feed(n=40)
        self.assertEqual(sum(1 for r in self.owner.requests if r['op'] == 'pulse'), 0)


class SafetySurface(unittest.TestCase):
    def test_only_the_lifted_request_topic_is_ever_published(self):
        src = (SCRIPTS / 'atlas_testlab_web.py').read_text().split('from __future__', 1)[1]   # code only, not the docstring
        self.assertEqual(src.count('create_publisher'), 2)           # both create the REQUEST_TOPIC publisher
        self.assertEqual(src.count('REQUEST_TOPIC'), 3)
        for banned in ('cmd_vel', 'Twist', 'joy', 'serial', '/dev/', 'subprocess', 'os.system', 'Rosmaster', 'voice/stop',
                       "'e_stop'", 'steering', 'create_client', 'Trigger'):
            self.assertFalse(banned in src, banned)

    def test_status_web_hook_is_the_only_integration(self):
        src = (SCRIPTS / 'atlas_status_web.py').read_text()
        self.assertEqual(src.count('atlas_testlab_web.serve'), 2)


if __name__ == '__main__':
    unittest.main()
