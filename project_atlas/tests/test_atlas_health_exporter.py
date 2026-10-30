"""ATLAS health exporter: read-only, never invents values, flags stale data, survives missing sources."""
import json
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_health_exporter as E   # noqa: E402

LINE = re.compile(r'^[a-z_][a-z0-9_]*(\{([a-z_]+="[^"\\\n]*",?)*\})? -?[0-9.e+-]+$')


def sysroot(cpu=('cpu 100 0 100 800 0 0 0 0 0 0', 'cpu 200 0 200 1600 0 0 0 0 0 0')):
    root = Path(tempfile.mkdtemp())
    (root / 'proc').mkdir()
    (root / 'proc/meminfo').write_text('MemTotal: 8000000 kB\nMemAvailable: 3000000 kB\nSwapTotal: 4000000 kB\nSwapFree: 4000000 kB\n')
    (root / 'proc/loadavg').write_text('7.5 7.0 6.9 3/900 1\n')
    for i, t in enumerate(('62000', None, '64000')):
        z = root / f'sys/class/thermal/thermal_zone{i}'; z.mkdir(parents=True)
        (z / 'type').write_text('cpu-thermal' if i == 0 else 'gpu-thermal')
        if t is None:
            (z / 'temp').mkdir()                      # unreadable zone, as on the Jetson
        else:
            (z / 'temp').write_text(t)
    g = root / 'sys/devices/platform/bus@0/17000000.gpu'; g.mkdir(parents=True); (g / 'load').write_text('250')
    f = root / 'sys/class/devfreq/17000000.gpu'; f.mkdir(parents=True); (f / 'cur_freq').write_text('306000000')
    return NS(path=root, cpu=list(cpu))


def api(age=0.1, enc_faults=(), down=False, policy_fresh=True):
    st = {'ros': {
        'lidar': {'age': 0.5, 'observed_hz': 1.8, 'value': {}},
        'motor_speed': {'age': age, 'observed_hz': 1.79, 'value': 0.0},
        'encoder_health': {'age': 0.0, 'value': json.dumps({'state': 'READY', 'faults': list(enc_faults), 'serial_checksum_errors': 0,
                                                            'serial_write_errors': 1, 'link_stale_events': 0, 'link_recoveries': 0})},
        'joy': {'age': 0.0, 'observed_hz': 16.2}, 'control_policy': {'age': 0.0, 'observed_hz': 10.0},
        'camera_info': {'age': 0.7, 'observed_hz': 0.95}, 'bms_voltage': {'age': 4.2, 'value': 13.1},
        'bat_voltage': {'age': 0.8, 'value': 12.3}, 'bms_percent': {'age': 4.2, 'value': 83.3},
        'bms_power': {'age': 4.2, 'value': -30.13}, 'enc_m1': {'age': 0.1, 'value': 42}, 'bms_current': {'age': 4.2, 'value': -2.3}, 'jetson_power': {'age': 0.7, 'value': 7.5}, 'cmd_vel': {'age': 1736.8, 'value': {'lin': 0.0, 'ang': 0.0}}}}
    mc = {'policy': {'age_s': 0.1, 'fresh': policy_fresh, 'stop_latched': True, 'manual_controller': 'FLYSKY', 'flysky_drive_enabled': True},
          'drive': {'age_s': 0.1, 'running': True, 'status': {'state': 'STOP_LATCHED', 'frame_age_s': 0.06, 'inputs': {'failsafe': False, 'frame_lost': False}}}}

    def get(path):
        if down:
            raise OSError('connection refused')
        return {'/api/status': st, '/api/manual_controller': mc}[path]
    return get


def run_ok(*a, **k):
    out = ('Id=atlas-cmd-vel-mux.service\nLoadState=loaded\nActiveState=active\nNRestarts=2\n\n'
           'Id=atlas-nav2.service\nLoadState=not-found\nActiveState=inactive\nNRestarts=0\n\n'
           'Id=atlas-lidar.service\nLoadState=loaded\nActiveState=failed\nNRestarts=5')
    return NS(returncode=0, stdout=out)


def metrics(text):
    out = {}
    for line in text.strip().splitlines():
        assert LINE.match(line), line
        k, v = line.rsplit(' ', 1)
        out[k] = float(v)
    return out


class Collect(unittest.TestCase):
    def setUp(self):
        E.STATE['cpu'] = None

    def two(self, root, **kw):
        stat = root.path / 'proc/stat'
        stat.write_text(root.cpu[0] + '\n'); E.collect(sysroot=str(root.path), **kw)
        stat.write_text(root.cpu[1] + '\n'); return metrics(E.collect(sysroot=str(root.path), **kw))

    def test_real_values_and_valid_exposition(self):
        m = self.two(sysroot(), get=api(), run=run_ok)
        self.assertAlmostEqual(m['atlas_cpu_utilization_percent'], 20.0)        # 200 busy of 1000 jiffies
        self.assertEqual(m['atlas_thermal_max_celsius'], 64.0)
        self.assertEqual(m['atlas_gpu_load_percent'], 25.0); self.assertEqual(m['atlas_gpu_frequency_hz'], 306000000)
        self.assertEqual(m['atlas_battery_voltage_volts{source="bms"}'], 13.1)
        self.assertEqual(m['atlas_control_selected{controller="FLYSKY"}'], 1); self.assertEqual(m['atlas_estop_latched'], 1)
        self.assertEqual(m['atlas_topic_rate_hz{topic="joy"}'], 16.2)
        self.assertEqual(m['atlas_encoder_ready'], 1); self.assertEqual(m['atlas_encoder_serial_write_errors_total'], 1)
        self.assertEqual(m['atlas_service_restarts_total{service="atlas-lidar"}'], 5)
        self.assertEqual(m['atlas_service_failed{service="atlas-lidar"}'], 1)

    def test_unreadable_thermal_zone_is_skipped_not_zero(self):
        m = self.two(sysroot(), get=api(), run=run_ok)
        zones = [k for k in m if k.startswith('atlas_thermal_celsius')]
        self.assertEqual(len(zones), 2); self.assertTrue(all(m[z] > 0 for z in zones))

    def test_first_collection_has_no_cpu_value(self):
        r = sysroot(); (r.path / 'proc/stat').write_text(r.cpu[0] + '\n')
        self.assertNotIn('atlas_cpu_utilization_percent', metrics(E.collect(sysroot=str(r.path), get=api(), run=run_ok)))

    def test_stale_topic_is_flagged_with_its_real_age(self):
        m = self.two(sysroot(), get=api(age=7.5), run=run_ok)
        self.assertEqual(m['atlas_topic_stale{topic="motor_speed"}'], 1)
        self.assertEqual(m['atlas_topic_age_seconds{topic="motor_speed"}'], 7.5)
        self.assertEqual(m['atlas_topic_stale{topic="lidar"}'], 0)

    def test_missing_sources_are_unavailable_never_zero(self):
        m = self.two(sysroot(), get=api(down=True), run=run_ok)
        self.assertEqual(m['atlas_source_available{source="dashboard_api"}'], 0)
        for k in m:
            self.assertFalse(k.startswith(('atlas_topic_', 'atlas_battery', 'atlas_estop', 'atlas_encoder', 'atlas_control')), k)
        self.assertIn('atlas_memory_available_bytes', m)                          # local metrics still work
        m = self.two(sysroot(), get=api(), run=run_ok)
        self.assertNotIn('atlas_topic_available{topic="us_validity"}', [k for k, v in m.items() if v == 1])
        self.assertEqual(m['atlas_topic_available{topic="us_validity"}'], 0)
        self.assertEqual(m['atlas_source_available{source="astra"}'], 0)
        self.assertEqual(m['atlas_service_loaded{service="atlas-nav2"}'], 0)
        self.assertNotIn('atlas_service_active{service="atlas-nav2"}', m)           # not installed: not "down"

    def test_stale_policy_hides_control_state(self):
        m = self.two(sysroot(), get=api(policy_fresh=False), run=run_ok)
        self.assertNotIn('atlas_estop_latched', m); self.assertEqual(m['atlas_source_available{source="control_policy"}'], 0)

    def test_idle_command_age_is_not_staleness(self):
        m = self.two(sysroot(), get=api(), run=run_ok)
        self.assertEqual(m['atlas_command_age_seconds'], 1736.8)
        self.assertNotIn('atlas_topic_stale{topic="cmd_vel"}', m)

    def test_systemd_failure_is_reported(self):
        m = self.two(sysroot(), get=api(), run=lambda *a, **k: NS(returncode=1, stdout=''))
        self.assertEqual(m['atlas_source_available{source="systemd"}'], 0)


class InvalidCache(unittest.TestCase):
    def render(self, status=None, control=None):
        base = api()
        def get(path):
            value = base(path)
            mutate = status if path == '/api/status' else control
            if mutate:
                mutate(value)
            return value
        out = E.Out(); E.collect_rover(out, get)
        return metrics(out.text())

    def test_invalid_ages_never_healthy(self):
        for age in (None, True, -1, float('nan'), float('inf'), '0'):
            with self.subTest(age=age):
                m = self.render(status=lambda s: s['ros']['lidar'].update(age=age))
                self.assertEqual(m['atlas_topic_available{topic="lidar"}'], 0)
                self.assertNotIn('atlas_topic_stale{topic="lidar"}', m)

    def test_missing_boolean_not_clear(self):
        m = self.render(control=lambda s: s['policy'].pop('stop_latched'))
        self.assertNotIn('atlas_estop_latched', m)
        m = self.render(control=lambda s: s['drive']['status']['inputs'].clear())
        self.assertNotIn('atlas_flysky_failsafe', m)

    def test_stale_policy_even_with_fresh_flag(self):
        for age in (None, True, -1, 1.01, float('nan')):
            m = self.render(control=lambda s: s['policy'].update(age_s=age))
            self.assertNotIn('atlas_estop_latched', m)
            self.assertEqual(m['atlas_source_available{source="control_policy"}'], 0)

    def test_stale_flysky_status_not_clear(self):
        m = self.render(control=lambda s: s['drive'].update(age_s=2))
        self.assertNotIn('atlas_flysky_failsafe', m)
        self.assertNotIn('atlas_flysky_frame_age_seconds', m)
        self.assertEqual(m['atlas_source_available{source="flysky_status"}'], 0)

    def test_incomplete_encoder_payload_not_ready_or_fault_free(self):
        m = self.render(status=lambda s: s['ros']['encoder_health'].update(value={}))
        self.assertNotIn('atlas_encoder_ready', m)
        self.assertNotIn('atlas_encoder_faults', m)

    def test_new_metrics_and_stale_omission(self):
        m = self.render()
        self.assertEqual(m['atlas_encoder_count{wheel="M1"}'], 42)
        self.assertEqual(m['atlas_battery_power_watts{source="bms"}'], -30.13)
        m = self.render(status=lambda s: s['ros']['enc_m1'].update(age=2))
        self.assertNotIn('atlas_encoder_count{wheel="M1"}', m)

    def test_bad_cache_structure_unavailable(self):
        m = self.render(status=lambda s: s.update(ros=[]))
        self.assertEqual(m['atlas_source_available{source="dashboard_api"}'], 0)


class Server(unittest.TestCase):
    def setUp(self):
        self.srv = E.ThreadingHTTPServer(('127.0.0.1', 0), E.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()

    def code(self, path, method='GET'):
        try:
            return urllib.request.urlopen(urllib.request.Request(self.url + path, method=method, data=b'' if method != 'GET' else None), timeout=2).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_read_only_and_stale_handling(self):
        E.LATEST, E.LAST = None, 0.0
        self.assertEqual(self.code('/metrics'), 503)                               # nothing collected yet
        E.LATEST, E.LAST = 'atlas_x 1\n', E.time.time()
        self.assertEqual(self.code('/metrics'), 200)
        E.LAST = E.time.time() - 60
        self.assertEqual(self.code('/metrics'), 503)                               # stale: never serve old data as live
        for m in ('POST', 'PUT', 'DELETE'):
            self.assertEqual(self.code('/metrics', m), 405)
        self.assertEqual(self.code('/'), 404)

    def test_bind_must_be_private_lan(self):
        for bad in ('0.0.0.0', '127.0.0.1', '8.8.8.8'):
            with self.assertRaises(SystemExit):
                sys.argv = ['x', '--bind', bad]; E.main()

    def test_no_ros_and_no_commands_in_source(self):
        code = (ROOT / 'scripts/atlas_health_exporter.py').read_text().split('"""', 2)[2]
        for bad in ('rclpy', 'import ros', 'cmd_vel_', '.publish(', 'create_publisher', 'import serial', 'serial.Serial',
                    "method='POST'", '/api/estop', 'select_'):
            self.assertFalse(bad in code, bad)


if __name__ == '__main__':
    unittest.main()
