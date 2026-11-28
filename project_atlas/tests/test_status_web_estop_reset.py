"""Stage 1b: authenticated web reset of the software E-STOP latch (server-side checks)."""
import email.message
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_status_web_estop_safety import Recorder, post, web  # noqa: E402  (installs ROS stubs)

ER = web.estop_reset
PIN = '482913'
ORIGIN = {'Origin': 'http://localhost:8088', 'Host': 'localhost:8088', 'X-Atlas-Wifi': '1'}


def request(method, path, body=None, headers=None, client='127.0.0.1'):
    h = web.Handler.__new__(web.Handler)
    raw = json.dumps(body).encode() if body is not None else b''
    msg = email.message.Message()
    msg['Content-Type'] = 'application/json'; msg['Content-Length'] = str(len(raw))
    for k, v in (headers or {}).items(): msg[k] = v
    h.headers, h.rfile, h.wfile = msg, io.BytesIO(raw), io.BytesIO()
    h.path, h.command, h.request_version, h.requestline = path, method, 'HTTP/1.1', f'{method} {path} HTTP/1.1'
    h.client_address, h.close_connection = (client, 5555), True
    (h.do_POST if method == 'POST' else h.do_GET)()
    out = h.wfile.getvalue().decode()
    return int(out.split(' ', 2)[1]), json.loads(out.split('\r\n\r\n', 1)[1])


class ResetBase(unittest.TestCase):
    def setUp(self):
        self._ros = web.ROS; web.SHUTDOWN_PENDING.clear()
        self.r = Recorder(policy={'stop_latched': True, 'stop_reason': 'REMOTE STOP: voice stop requested'})
        web.ROS = self.r
        self.r.reset_pins.set(PIN)
        self.healthy()

    def tearDown(self):
        web.ROS = self._ros; web.SHUTDOWN_PENDING.clear()

    def healthy(self, latched=True):
        now = time.time(); d = self.r.data
        d['control_policy'] = {'value': json.dumps({'stop_latched': latched, 'stop_reason': 'REMOTE STOP: voice stop requested'}), 'ts': now}
        d['joy'] = {'value': {'axes': 8, 'buttons': 11}, 'ts': now}
        d['odom'] = {'value': {'x': 0, 'y': 0, 'vx': 0.0, 'wz': 0.0}, 'ts': now}
        d['cmd_vel'] = {'value': {'lin': 0.0, 'ang': 0.0}, 'ts': now}

    def state(self, client='127.0.0.1'):
        return request('GET', '/api/estop/state', client=client)[1]

    def reset(self, nonce, pin=PIN, headers=ORIGIN, confirm=ER.CONFIRM_PHRASE, client='127.0.0.1'):
        return request('POST', '/api/estop/reset', {'nonce': nonce, 'pin': pin, 'confirm': confirm}, headers, client)


class StateAndConditions(ResetBase):
    def test_available_with_challenge_when_all_conditions_hold(self):
        s = self.state()
        self.assertTrue(s['latched']); self.assertTrue(s['reset']['available']); self.assertTrue(s['reset']['challenge'])
        self.assertEqual(s['reset']['blocked'], [])

    def test_each_unsafe_or_unknown_condition_blocks(self):
        now = time.time()
        cases = {
            'physical remote not connected': lambda d: d['joy'].update(ts=now - 2),
            'odometry stale': lambda d: d['odom'].update(ts=now - 2),
            'rover not stationary': lambda d: d['odom']['value'].update(vx=0.2),
            '/cmd_vel stale': lambda d: d['cmd_vel'].update(ts=now - 3),
            'motor command not zero': lambda d: d['cmd_vel']['value'].update(lin=0.3),
            'mux policy stale': lambda d: d['control_policy'].update(ts=now - 3),
        }
        for why, mutate in cases.items():
            self.healthy(); mutate(self.r.data)
            s = self.state()
            self.assertFalse(s['reset']['available'], why); self.assertIsNone(s['reset']['challenge'])
            self.assertTrue(any(why in b for b in s['reset']['blocked']), (why, s['reset']['blocked']))

    def test_drive_pressed_recently_shutdown_no_pin_or_ros_down_block(self):
        self.r.last_drive_request = time.monotonic() - 0.5
        self.assertIn('a drive button is still pressed (release all drive buttons)', self.state()['reset']['blocked'])
        self.r.last_drive_request = float('-inf'); self.r.drive_active = True
        self.assertFalse(self.state()['reset']['available']); self.r.drive_active = False
        web.SHUTDOWN_PENDING.set(); self.assertIn('shutdown in progress', self.state()['reset']['blocked']); web.SHUTDOWN_PENDING.clear()
        self.r.reset_pins.path.unlink(); self.assertIn('no operator PIN configured on ATLAS', self.state()['reset']['blocked'])
        self.r.reset_pins.set(PIN); self.r.ready = False
        self.assertIn('ROS link not ready', self.state()['reset']['blocked'])

    def test_not_latched_offers_no_reset(self):
        self.healthy(latched=False); s = self.state()
        self.assertFalse(s['latched']); self.assertFalse(s['reset']['available']); self.assertIsNone(s['reset']['challenge'])


class ResetRequest(ResetBase):
    def test_granted_reset_zeroes_first_then_asks_mux_and_requires_fresh_press(self):
        nonce = self.state()['reset']['challenge']
        code, p = self.reset(nonce)
        self.assertEqual(code, 200, p); self.assertTrue(p['released'])
        self.assertEqual(self.r.events, [('TWIST', 0.0, 0.0)])          # only zero, nothing else
        self.assertEqual(self.r.mux_reset_calls, 1); self.assertTrue(self.state()["drive_requires_fresh_press"])
        self.assertEqual(self.r.log_lines[-1]['event'], 'reset_granted')
        self.assertNotIn(PIN, json.dumps(self.r.log_lines))

    def test_rejections(self):
        n = lambda: self.state()['reset']['challenge']
        self.assertEqual(self.reset(n(), headers={})[0], 403)                                   # not from the dashboard page
        self.assertEqual(self.reset(n(), headers={**ORIGIN, 'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.reset(n(), confirm='yes')[0], 400)                                # no explicit confirmation
        self.assertEqual(self.reset('made-up')[0], 409)                                         # unknown challenge
        used = n(); self.assertEqual(self.reset(used)[0], 200)
        self.healthy()
        self.assertEqual(self.reset(used)[0], 409)                                              # single use
        other = self.state(client='192.168.1.50')['reset']['challenge']
        self.assertEqual(self.reset(other, client='192.168.1.60')[0], 409)                      # bound to the client
        self.assertEqual(self.r.mux_reset_calls, 1)

    def test_stale_challenge_rejected(self):
        clock = [1000.0]; self.r.reset_challenges = ER.Challenges(clock=lambda: clock[0])
        nonce = self.state()['reset']['challenge']; clock[0] += ER.CHALLENGE_TTL_S + 0.1
        self.assertEqual(self.reset(nonce)[0], 409); self.assertEqual(self.r.mux_reset_calls, 0)

    def test_conditions_rechecked_at_reset_time(self):
        nonce = self.state()['reset']['challenge']
        self.r.data['odom']['value']['vx'] = 0.3                     # rover moved after the page showed AVAILABLE
        code, p = self.reset(nonce)
        self.assertEqual(code, 409); self.assertIn('rover not stationary', p['message']); self.assertEqual(self.r.mux_reset_calls, 0)

    def test_wrong_pin_then_lockout_even_for_the_right_pin(self):
        for _ in range(ER.MAX_FAILURES):
            self.assertEqual(self.reset(self.state()['reset']['challenge'], pin='000000')[0], 403)
        s = self.state(); self.assertFalse(s['reset']['available']); self.assertGreater(s['reset']['lockout_s'], 0)
        code, _ = self.reset('anything'); self.assertEqual(code, 429)
        self.assertEqual(self.r.mux_reset_calls, 0)
        self.assertEqual(sum(1 for l in self.r.log_lines if l['event'] == 'reset_denied_pin'), ER.MAX_FAILURES)
        self.assertNotIn('000000', json.dumps(self.r.log_lines))

    def test_mux_refusal_keeps_latch(self):
        self.r.mux_reset_reply = (False, 'Keep sticks centred and all buttons released for one second')
        code, p = self.reset(self.state()['reset']['challenge'])
        self.assertEqual(code, 409); self.assertFalse(p['released']); self.assertIn('stop multiplexer', p['message'])
        self.assertTrue(self.r.drive_stop_latched(estop_grace_s=0.0))


class AfterReset(ResetBase):
    def drive(self, press=None, start=False):
        f = {'action': 'drive', 'linear': '.65', 'angular': '0'}
        if press: f.update(press=press, start='1' if start else '0')
        return post(f)

    def test_presses_from_before_the_reset_never_resume(self):
        self.assertEqual(self.drive('held', start=True)[0], 409)        # pressed while latched: refused, but its start is recorded
        self.r.last_drive_request = float('-inf')                          # (buttons released before the reset)
        self.reset(self.state()['reset']['challenge']); self.r.events.clear()
        for _ in range(5):
            self.assertEqual(self.drive('held')[0], 409)                   # repeats of the pre-reset press
            self.assertEqual(self.drive('lost-in-network')[0], 409)        # a press whose start never arrived
            self.assertEqual(self.drive()[0], 409)                          # an old page without press ids
        self.assertTrue(all(e == ('TWIST', 0.0, 0.0) for e in self.r.events))
        code, p = self.drive(); self.assertIn('Reload', p['message'])

    def test_a_new_press_after_the_reset_drives(self):
        self.reset(self.state()['reset']['challenge']); self.r.events.clear()
        self.assertEqual(self.drive('new', start=True)[0], 200)
        self.assertEqual(self.drive('new')[0], 200)                        # its repeats
        self.assertIn(('TWIST', 0.65, 0.0), self.r.events)
        self.assertFalse(self.state()['drive_requires_fresh_press'])

    def test_remote_release_also_requires_a_fresh_press(self):
        self.drive('before', start=True)                                   # latched: refused, start recorded
        self.r.note_latch_state()                                          # server sees latched
        self.healthy(latched=False); self.r.web_estop_at = float('-inf')
        self.r.note_latch_state()                                          # ... then released (by the remote)
        self.assertEqual(self.drive('before')[0], 409)
        self.assertTrue(self.state()['drive_requires_fresh_press'])
        self.assertEqual(self.drive('after', start=True)[0], 200)

    def test_state_polling_and_network_silence_never_release(self):
        for _ in range(20): self.state()
        self.assertTrue(self.r.drive_stop_latched(estop_grace_s=0.0)); self.assertEqual(self.r.mux_reset_calls, 0)


class PinAndLog(unittest.TestCase):
    def test_pin_store_hashes_with_private_mode(self):
        with tempfile.TemporaryDirectory() as d:
            s = ER.PinStore(Path(d) / 'p.json'); self.assertFalse(s.configured())
            for bad in ('12345', 'abcdef', '1234567890123'):
                with self.assertRaises(ValueError): s.set(bad)
            s.set(PIN); raw = s.path.read_text()
            self.assertNotIn(PIN, raw); self.assertEqual(stat.S_IMODE(os.stat(s.path).st_mode), 0o600)
            self.assertTrue(s.verify(PIN)); self.assertFalse(s.verify('482914')); self.assertFalse(s.verify(None))

    def test_event_log_appends_rotates_and_drops_pin_field(self):
        with tempfile.TemporaryDirectory() as d:
            log = ER.EventLog(Path(d) / 'e.jsonl'); old = ER.LOG_MAX_BYTES; ER.LOG_MAX_BYTES = 300
            try:
                for i in range(20): log.write('stop', client='x', pin=PIN, n=i)
            finally:
                ER.LOG_MAX_BYTES = old
            files = sorted(p.name for p in Path(d).iterdir())
            self.assertIn('e.jsonl.1', files); self.assertLessEqual(len(files), ER.LOG_KEEP + 1)
            text = ''.join(p.read_text() for p in Path(d).iterdir())
            self.assertNotIn(PIN, text); self.assertIn('"event":"stop"', text)


class StopsAreLogged(ResetBase):
    def test_stop_and_e_stop_events_logged(self):
        post({'action': 'stop'}); post({'action': 'e_stop'})
        self.assertEqual([l['event'] for l in self.r.log_lines[-2:]], ['stop', 'e_stop'])
        self.assertTrue(self.r.log_lines[-1]['latched'])


if __name__ == '__main__':
    unittest.main()
