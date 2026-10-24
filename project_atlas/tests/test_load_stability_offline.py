"""Offline tests for atlas_load_stability_test.py: fake Dashboard + fake thermal zones; real CPU load on this host."""
import json, os, subprocess, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; TOOL = ROOT / 'tools/diagnostics/atlas_load_stability_test.py'


class Fake:
    def __init__(self):
        self.c = {}; o = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                c = o.c; pol = {'stop_latched': True, 'manual_only': True, 'commission_armed': False, 'source': c.get('source', 'STOPPED')}
                ros = {k: {'value': 1, 'age': c.get('age_' + k, 0.1), 'observed_hz': 10.0} for k in ('lidar', 'odom', 'imu_yaw', 'enc_m1', 'enc_m2', 'enc_m3', 'enc_m4', 'amcl_quality', 'drive_pid')}
                ros.update(control_policy={'value': json.dumps(pol), 'age': 0.2}, cmd_vel={'value': {'lin': 0.0, 'ang': 0.0}, 'age': 0.1}, mission_status={'value': 'READY', 'age': 0.3})
                body = json.dumps({'ros': ros} if self.path.startswith('/api/status') else {'latched': c.get('estop', True)}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.srv.server_address[1]


class LoadStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = Fake(); cls.tmp = tempfile.TemporaryDirectory(); cls.th = Path(cls.tmp.name) / 'thermal'
        (cls.th / 'thermal_zone0').mkdir(parents=True); cls.set_temp(55.0)

    @classmethod
    def set_temp(cls, c): (cls.th / 'thermal_zone0' / 'temp').write_text(str(int(c * 1000)))

    def setUp(self):
        self.f.c = {}; self.set_temp(55.0)

    def run_tool(self, *args, approved=True, during=None):
        env = dict(os.environ, ATLAS_DASHBOARD_URL=self.f.url, ATLAS_THERMAL_ROOT=str(self.th), OWNER_APPROVED='yes' if approved else '')
        out = Path(self.tmp.name) / ('o%d' % time.monotonic_ns())
        p = subprocess.Popen([sys.executable, str(TOOL), *args, '--out', str(out)], env=env, stdout=subprocess.PIPE, text=True)
        if during: threading.Timer(during[0], during[1]).start()
        lines = p.stdout.read().splitlines(); p.wait(200)
        rows = [json.loads(l) for l in lines if l.startswith('{')]
        return p.returncode, rows

    def test_pass_holds_target_and_reports(self):
        rc, rows = self.run_tool('run', '--target', '70', '--baseline-s', '5', '--load-s', '32', '--recovery-s', '3')
        v = rows[-1]
        self.assertEqual(v['event'], 'verdict', rows[-3:]); self.assertEqual(v['verdict'], 'PASS', v['checks'])
        self.assertEqual(rc, 0); self.assertLess(v['busy']['recovery'], 50)        # load removed afterwards

    def _abort_case(self, trigger):
        rc, rows = self.run_tool('run', '--target', '70', '--baseline-s', '3', '--load-s', '60', '--recovery-s', '3', during=(12, trigger))
        v = rows[-1]
        self.assertEqual(v['verdict'], 'FAIL'); self.assertIsNotNone(v['aborted']); self.assertEqual(rc, 1)
        ticks = [r for r in rows if 'phase' in r]
        self.assertLess(ticks[-1]['t'], 20, 'abort must happen within seconds of the fault')
        return v

    def test_abort_on_stale_sensor(self):
        v = self._abort_case(lambda: self.f.c.update(age_lidar=5.0)); self.assertIn('lidar', str(v['aborted']['reasons']))

    def test_abort_on_estop_released(self):
        v = self._abort_case(lambda: self.f.c.update(estop=False)); self.assertIn('E-STOP', str(v['aborted']['reasons']))

    def test_abort_on_temperature(self):
        v = self._abort_case(lambda: self.set_temp(70.5)); self.assertIn('temperature', str(v['aborted']['reasons']))

    def test_refusals(self):
        rc, rows = self.run_tool('run', approved=False); self.assertEqual(rc, 2)
        rc, rows = self.run_tool('run', '--target', '95'); self.assertEqual(rc, 2)
        self.f.c = {'source': 'WEB'}; rc, rows = self.run_tool('run', '--target', '70'); self.assertEqual(rc, 2); self.assertIn('policy', rows[-1]['reason'])
        self.f.c = {'age_enc_m1': 9.0}; rc, rows = self.run_tool('check'); self.assertEqual(rc, 2)
        self.f.c = {}; self.set_temp(68.5); rc, rows = self.run_tool('check'); self.assertEqual(rc, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
