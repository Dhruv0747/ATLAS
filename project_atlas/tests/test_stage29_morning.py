"""Stage 29 morning helper: the precheck is GO only for the exact safe starting state, and the helper is read-only."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/deploy/stage29_flysky_drive'))
import stage29_morning as H   # noqa: E402


def world(**over):
    w = {'gate': True, 'reviewed': True, 'limits': (0.05, 0.20), 'latched': True, 'ctl': 'XBOX', 'can_fs': True,
         'drive': 'NOT_SELECTED', 'xb': 'LIVE', 'buttons': [0] * 11, 'fs': 'LIVE', 'failsafe': False,
         'raw': {1: 1024, 2: 1024, 5: 240, 6: 240, 7: 1024}, 'motor': 0.0, 'move': False, 'feature': 'inactive',
         'lease': False, 'cpu': 63.0}
    w.update(over)
    return w


def run(w, temp=62.0):
    tmp = Path(tempfile.mkdtemp())
    if w['gate']:
        for u in ('atlas-cmd-vel-mux.service', 'atlas-flysky-teleop.service'):
            d = tmp / f'systemd/user/{u}.d'; d.mkdir(parents=True); (d / '90-atlas-flysky-gate.conf').write_text('x')
    if w['lease']:
        (tmp / 'atlas-mux-maintenance').mkdir(); (tmp / 'atlas-mux-maintenance/lease.json').write_text('{}')
    n = {'status': 0}

    def get(path):
        if path.startswith('/api/manual_controller'):
            return {'policy': {'fresh': True, 'stop_latched': w['latched'], 'stop_reason': 'x', 'manual_controller': w['ctl'],
                               'flysky_drive_enabled': w['gate']},
                    'drive': {'running': True, 'status': {'state': w['drive'], 'config': {
                        'reviewed_by_owner': w['reviewed'], 'errors': [], 'max_linear_mps': w['limits'][0], 'max_angular_radps': w['limits'][1]}}},
                    'can_select': {'XBOX': False, 'FLYSKY': w['can_fs']}, 'blocked_reason': ''}
        if path.startswith('/api/controller_inputs'):
            return {'xbox': {'state': w['xb'], 'layout_ok': True, 'rate_hz': 16.0, 'axes': [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0], 'buttons': w['buttons']}}
        if path.startswith('/api/flysky/state'):
            return {'link': {'state': w['fs']}, 'flags': {'failsafe': w['failsafe'], 'frame_lost': False},
                    'channels': [{'channel': c, 'raw': v} for c, v in w['raw'].items()]}
        if path == '/api/status':
            n['status'] += 1
            e = 100 + (n['status'] if w['move'] else 0)
            return {'ros': {'motor_speed': {'value': w['motor']}, 'cmd_vel': {'value': {'lin': 0.0, 'ang': 0.0}},
                            **{f'enc_m{i}': {'value': e} for i in (1, 2, 3, 4)},
                            'encoder_health': {'value': json.dumps({'state': 'READY'})}}}
        raise AssertionError(path)
    with mock.patch.object(H.time, 'sleep', lambda s: None):
        res = H.checks(get=get, systemctl=lambda *a: w['feature'], resources=lambda: (w['cpu'], 60.0, temp), runtime=tmp)
    return {item: ok for ok, item, _ in res}


def run_with_temp(w, temp):
    return run(w, temp)


class Precheck(unittest.TestCase):
    def test_safe_morning_state_is_go(self):
        r = run(world()); self.assertTrue(all(r.values()), [k for k, v in r.items() if not v])

    def test_every_unsafe_condition_is_no_go(self):
        cases = {'gate': False, 'reviewed': False, 'limits': (0.15, 0.6), 'latched': False, 'ctl': 'FLYSKY', 'can_fs': False,
                 'xb': 'LOST', 'buttons': [0, 0, 0, 0, 1] + [0] * 6, 'fs': 'FAILSAFE', 'failsafe': True,
                 'raw': {1: 1024, 2: 1300, 5: 1807, 6: 1024, 7: 240}, 'motor': 0.3, 'move': True, 'feature': 'active',
                 'lease': True, 'cpu': 90.0}
        for k, v in cases.items():
            r = run(world(**{k: v}))
            self.assertFalse(all(r.values()), f'{k}={v} was GO')

    def test_temperature_unknown_or_hot_is_no_go(self):
        for temp in (None, 71.0):
            with self.subTest(temp=temp):
                tmp = world()
                r = run_with_temp(tmp, temp)
                self.assertFalse(r['CPU / RAM / temperature within limits'])

    def test_unreadable_thermal_zones_are_skipped(self):
        d = Path(tempfile.mkdtemp()); (d / 'a').write_text('55000\n'); (d / 'b').write_text('61500\n')
        self.assertEqual(H.max_temp([str(d / 'a'), str(d / 'missing'), str(d / 'b')]), 61.5)
        self.assertIsNone(H.max_temp([str(d / 'missing')]))

    def test_helper_is_read_only(self):
        src = (ROOT / 'tools/deploy/stage29_flysky_drive/stage29_morning.py').read_text()
        code = re.sub(r'"""[\s\S]*?"""', '', src)
        for bad in ("method='POST'", 'data=', '/api/estop', 'select_', "'restart'", "'start',", "'stop',", 'publish', 'serial'):
            self.assertNotIn(bad, code, bad)
        self.assertIn("'systemd-run'", code)                     # only to start the read-only recorder


if __name__ == '__main__':
    unittest.main()
