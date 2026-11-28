"""Dashboard FIX MY LOCATION (2026-11-21): gates, single run, verdict reporting. No ROS, no real seeding."""
import email.message
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_relocalize_web as rw  # noqa: E402


class FakeProc:
    def __init__(self, rc=0, out='', err=''):
        self.returncode, self.stdout, self.stderr = rc, out, err


def wait_done(r, timeout=15.0):
    end = time.time() + timeout
    while r.status()['running'] and time.time() < end:
        time.sleep(0.01)


class RelocalizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.verdict = Path(self.tmp.name) / 'verdict.json'
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner_writing(self, record, block=None):
        def run(cmd, **kw):
            self.calls.append(cmd)
            if block:
                block.wait(2)
            self.verdict.write_text(json.dumps(dict(record, written_unix=time.time())))
            return FakeProc()
        return run

    def test_refuses_when_armed_or_unknown(self):
        r = rw.Relocalizer(verdict_file=self.verdict, runner=self.runner_writing({}))
        for armed in (True, None):
            code, body = r.start(armed)
            self.assertEqual(code, 409)
            self.assertIn('AUTONOMY OFF', body['message'])
        self.assertEqual(self.calls, [])

    def test_runs_boot_verify_seeder_and_reports_seeded_pose(self):
        rec = {'mode': 'verify', 'seeded': True, 'reason': 'unique LiDAR match on the saved map',
               'attempts': [{'state': 'VERIFIED', 'best': {'x': -1.065, 'y': 0.185, 'yaw_deg': 12.0}, 'best_fit': 1.0}]}
        r = rw.Relocalizer(verdict_file=self.verdict, runner=self.runner_writing(rec))
        code, body = r.start(False)
        self.assertEqual(code, 202)
        wait_done(r)
        self.assertEqual(self.calls[0][-2:], ['--mode', 'verify'])
        self.assertTrue(self.calls[0][1].endswith('seed_atlas_localization.py'))
        last = r.status()['last']
        self.assertTrue(last['seeded'])
        self.assertEqual(last['state'], 'VERIFIED')
        self.assertEqual(last['pose'], {'x': -1.065, 'y': 0.185, 'yaw_deg': 12.0})
        self.assertEqual(last['fit'], 1.0)

    def test_unknown_verdict_is_reported_not_seeded(self):
        rec = {'mode': 'verify', 'state': 'UNKNOWN',
               'reason': 'scan does not match the saved map well enough anywhere (best 0.78 < 0.93)', 'attempts': []}
        r = rw.Relocalizer(verdict_file=self.verdict, runner=self.runner_writing(rec))
        r.start(False)
        wait_done(r)
        last = r.status()['last']
        self.assertFalse(last['seeded'])
        self.assertEqual(last['state'], 'UNKNOWN')
        self.assertIn('0.78', last['reason'])

    def test_one_run_at_a_time(self):
        gate = threading.Event()
        r = rw.Relocalizer(verdict_file=self.verdict, runner=self.runner_writing({'seeded': True}, block=gate))
        self.assertEqual(r.start(False)[0], 202)
        self.assertEqual(r.start(False)[0], 409)
        self.assertTrue(r.status()['running'])
        gate.set()
        wait_done(r)
        self.assertFalse(r.status()['running'])
        self.assertEqual(len(self.calls), 1)

    def test_no_new_verdict_is_an_error(self):
        r = rw.Relocalizer(verdict_file=self.verdict, runner=lambda cmd, **kw: FakeProc(1, '', 'AMCL not running'))
        r.start(False)
        wait_done(r)
        last = r.status()['last']
        self.assertEqual(last['state'], 'ERROR')
        self.assertIn('AMCL not running', last['reason'])

    def test_timeout_is_reported(self):
        def run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 150)
        r = rw.Relocalizer(verdict_file=self.verdict, runner=run)
        r.start(False)
        wait_done(r)
        self.assertIn('timed out', r.status()['last']['reason'])


class HttpGateTests(unittest.TestCase):
    def call(self, path, body=None, same=True, armed=False):
        h = mock.MagicMock()
        h.path = path
        msg = email.message.Message()
        raw = json.dumps(body).encode() if body is not None else b''
        msg['Content-Type'] = 'application/json'
        msg['Content-Length'] = str(len(raw))
        h.headers, h.rfile = msg, io.BytesIO(raw)
        out = {}
        resp = lambda handler, code, payload: out.update(code=code, payload=payload)
        fake_wifi = mock.MagicMock(same_origin=mock.MagicMock(return_value=same))
        with mock.patch.dict(sys.modules, {'atlas_wifi_web': fake_wifi}), \
             mock.patch.object(rw.RELOCALIZER, 'start', return_value=(202, {'ok': True})) as start:
            handled = rw.serve(h, lambda: armed, resp, post=body is not None)
        return handled, out, start

    def test_other_paths_not_handled(self):
        self.assertFalse(self.call('/api/status')[0])

    def test_post_requires_confirm_token(self):
        _, out, start = self.call('/api/relocalize', {'confirm': 'nope'})
        self.assertEqual(out['code'], 400)
        start.assert_not_called()

    def test_post_requires_same_origin(self):
        _, out, start = self.call('/api/relocalize', {'confirm': 'FIND_LOCATION'}, same=False)
        self.assertEqual(out['code'], 403)
        start.assert_not_called()

    def test_good_post_passes_armed_state(self):
        _, out, start = self.call('/api/relocalize', {'confirm': 'FIND_LOCATION'}, armed=False)
        self.assertEqual(out['code'], 202)
        start.assert_called_once_with(False)

    def test_get_returns_status(self):
        handled, out, _ = self.call('/api/relocalize')
        self.assertTrue(handled)
        self.assertEqual(out['code'], 200)
        self.assertFalse(out['payload']['navigation_authorized'])


if __name__ == '__main__':
    unittest.main()
