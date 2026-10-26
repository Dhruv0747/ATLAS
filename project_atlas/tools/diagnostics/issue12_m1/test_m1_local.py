import json, struct, threading, unittest, urllib.error
from unittest import mock
import m1_local as M


class FakeResp:
    def __init__(self, body, headers=None, status=200): self.body, self.headers, self.status = body, headers or {}, status
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


class T(unittest.TestCase):
    def test_failed_requests_never_raise(self):
        for err in (TimeoutError('timed out'), urllib.error.URLError('down'), ConnectionResetError(), ValueError('bad json')):
            h = M.Http(opener=mock.Mock(side_effect=err))
            ok, v, _ = h.call('lidar', '/api/lidar-view', 1)
            self.assertFalse(ok); self.assertEqual(h.log[-1]['ok'], False)

    def test_bad_json_recorded_not_raised(self):
        h = M.Http(opener=lambda *a, **k: FakeResp(b'{not json'))
        self.assertFalse(h.call('lease', '/api/vision3d/status', 1)[0])

    def test_client_never_sends_stop(self):
        src = open(M.__file__).read()
        self.assertNotIn("'action': 'stop'", src); self.assertNotIn('"action": "stop"', src)

    def test_lease_and_timeouts_are_bounded_and_not_extended(self):
        self.assertLessEqual(M.LEASE_PERIOD_S, 1.0); self.assertLessEqual(M.LEASE_TIMEOUT_S, 2.0)
        self.assertLessEqual(M.LEASE_PERIOD_S + M.LEASE_TIMEOUT_S, 4.0 - 1.0)   # one failed renewal still fits the 4-s lease

    def test_keepalive_survives_failures_and_ends_on_session_end(self):
        seq = [TimeoutError('x'), {'runtime': {'state': 'CHECKING'}}, {'runtime': {'state': 'ACTIVE', 'resources': {'cpu_percent': 60}}},
               TimeoutError('y'), {'runtime': {'state': 'ACTIVE'}}, {'runtime': {'state': 'OFF', 'reason': '60-second session complete'}}]
        def opener(*a, **k):
            x = seq.pop(0)
            if isinstance(x, Exception): raise x
            return FakeResp(json.dumps(x).encode())
        s = M.Session(M.Http(opener=opener), sleep=lambda _: None)
        s.keepalive()
        self.assertTrue(s.done.is_set()); self.assertEqual(s.states[-1][1], 'OFF')
        self.assertEqual(sum(not r['ok'] for r in s.http.log), 2)

    def test_measure_survives_failures(self):
        calls = {'n': 0}
        s = M.Session(M.Http(opener=mock.Mock(side_effect=TimeoutError('t'))), sleep=lambda _: None)
        def sleep(_):
            calls['n'] += 1
            if calls['n'] >= 3: s.done.set()
        s.sleep = sleep; s.measure()
        self.assertEqual(len(s.http.log), 3); self.assertEqual(s.depth, [])

    def test_cdr_stamp(self):
        buf = b'\x00\x01\x00\x00' + struct.pack('<iI', 1793030000, 500000000) + b'rest'
        self.assertAlmostEqual(M.cdr_stamp(buf), 1793030000.5)

    def test_roi_depth(self):
        w, h = 32, 24; body = struct.pack('<%dH' % (w * h), *([790] * (w * h)))
        d = M.roi_depth(body, {'X-Width': str(w), 'X-Height': str(h), 'X-Step': str(2 * w), 'X-Encoding': '16UC1'})
        self.assertEqual(d['center_m'], 0.79); self.assertEqual(d['valid'], 1.0)

    def test_probe_is_passive_private_domain_raw(self):
        src = open(M.__file__).read()
        self.assertIn('domain_id=77', src); self.assertIn('raw=True', src)
        for bad in ('Popen', 'subprocess', 'astra_camera_node', 'create_publisher', 'ROS_DOMAIN_ID'):
            self.assertNotIn(bad, src)


if __name__ == '__main__':
    unittest.main()
