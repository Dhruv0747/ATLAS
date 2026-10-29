"""Stage 29 FlySky mux patch, tested on the LIVE mux baseline (0d959286) with the real RemoteStop logic, no ROS."""
import ast
import dataclasses
import json
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage29_flysky_drive'
sys.path.insert(0, str(PKG)); sys.path.insert(0, str(ROOT / 'scripts'))
import insert_flysky_mux as patch          # noqa: E402
from atlas_remote_stop import RemoteStop   # noqa: E402

BASELINE = PKG / 'baseline/atlas_cmd_vel_mux.py.live-0d959286'
METHODS = {'moving', 'copy_twist', 'on_command', 'controller_accepts', 'select_controller', 'select_controller_service',
           'on_flysky_stop', 'hold_remote_stop', 'publish_stop', 'publish', 'live_channel', 'watchdog', 'publish_mode',
           'on_stop_joy'}


class Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class Twist:
    def __init__(self):
        self.linear, self.angular = Vec(), Vec()


def tw(x=0.0, z=0.0):
    t = Twist(); t.linear.x, t.angular.z = x, z; return t


class String:
    def __init__(self, data=''):
        self.data = data


def build(text, clock):
    tree = ast.parse(text)
    consts, keep = {}, []
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            for t in node.targets:
                consts[t.id] = ast.literal_eval(node.value)
        if isinstance(node, ast.ClassDef) and node.name == 'Channel':
            keep.append(node)
    mux = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AtlasCmdVelMux')
    mux.bases, mux.decorator_list = [], []
    mux.body = [n for n in mux.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
    scope = dict(time=NS(monotonic=clock), Twist=Twist, String=String, json=json, math=math, Optional=__import__("typing").Optional,
                 dataclass=dataclasses.dataclass, field=dataclasses.field, Dict=dict, **consts)
    exec(compile(ast.Module(body=keep + [mux], type_ignores=[]), 'mux_candidate', 'exec'), scope)
    return scope['AtlasCmdVelMux'], scope['Channel'], consts


class Base(unittest.TestCase):
    enabled = True

    def setUp(self):
        self.now = 100.0
        self.text = patch.apply(BASELINE.read_text())
        cls, Channel, self.consts = build(self.text, lambda: self.now)
        m = cls()
        m.remote_stop = RemoteStop()
        m.manual_only, m.commission_until = True, 0.0
        m.manual_controller, m.flysky_drive_enabled = 'XBOX', self.enabled
        m.flysky_max_linear, m.flysky_max_angular = 0.15, 0.60
        m.remote_linear_deadband, m.remote_angular_deadband, m.remote_steer_hold_s = 0.06, 0.12, 0.35
        m._remote_held_yaw = m._remote_last_steer_rx = m._remote_raw_steer = m._remote_raw_steer_rx = 0.0
        m.operating_mode = 'MANUAL'
        m.radar_gate_enabled = False                       # as on the rover (ATLAS_RADAR_GATE_ENABLED unset)
        m.encoder_health, m.encoder_health_rx = {}, 0.0
        m.mapping_remote_max_linear, m.mapping_remote_max_angular = 0.3, 1.2
        m.channels = {n: Channel(n, t, p, 0.35) for n, t, p in (
            ('REMOTE', '/cmd_vel_joy', 1), ('FLYSKY', '/cmd_vel_flysky', 1), ('COMMISSION', '/cmd_vel_commission', 2),
            ('RECOVERY', '/cmd_vel_recovery', 3), ('WEB', '/cmd_vel_web', 4), ('NAV2', '/cmd_vel_nav', 6))}
        m.active_name, m.last_sent = None, Twist()
        m._remote_stop_hold_latched = m._remote_stop_hold_reason = None
        m._remote_stop_last_zero = m._remote_stop_last_status = float('-inf')
        m.output, m.safety_output, m.mode_output, m.policy_output = Mock(), Mock(), Mock(), Mock()
        m.get_logger = lambda: NS(warn=lambda *a: None, error=lambda *a: None, info=lambda *a: None)
        self.m = m

    # helpers: drive the real RemoteStop like the Xbox does
    def joy(self, axes=(0, 0, 0, 0, 0, 0), buttons=(0,) * 11):
        self.m.on_stop_joy(NS(axes=list(axes), buttons=list(buttons)))

    def release(self):
        lb = [0] * 11; lb[4] = 1
        self.joy(); self.joy()
        for _ in range(25):
            self.now += 0.1; self.joy(buttons=lb)
        self.now += 0.05; self.joy()
        self.assertFalse(self.m.remote_stop.latched)

    def latch(self):
        b = [0] * 11; b[1] = 1
        self.now += 0.05; self.joy(buttons=b); self.now += 0.05; self.joy()
        self.assertTrue(self.m.remote_stop.latched)

    def last_out(self):
        return self.m.output.publish.call_args[0][0]

    def policy(self):
        return json.loads(self.m.policy_output.publish.call_args[0][0].data)


class PatchShape(Base):
    def test_applies_once_compiles_and_is_additive_except_the_allow_list(self):
        compile(self.text, 'c', 'exec')
        with self.assertRaises(SystemExit):
            patch.apply(self.text)
        old, new = BASELINE.read_text().splitlines(), self.text.splitlines()
        removed = [l for l in old if l not in new]
        self.assertEqual(removed, ["        if self.manual_only and name not in ('REMOTE', 'COMMISSION', 'RECOVERY'):"])

    def test_also_applies_to_the_repo_mux(self):
        compile(patch.apply((ROOT / 'scripts/atlas_cmd_vel_mux.py').read_text()), 'r', 'exec')

    def test_hard_ceilings_match_the_xbox_non_turbo_scales(self):
        joy = (ROOT / 'config/joy_config.yaml').read_text()
        self.assertIn('scale_linear.x: 0.25', joy); self.assertIn('scale_angular.yaw: 0.8', joy)
        self.assertEqual((self.consts['FLYSKY_HARD_MAX_LINEAR'], self.consts['FLYSKY_HARD_MAX_ANGULAR']), (0.25, 0.80))

    def test_drift_from_baseline_is_refused(self):
        with self.assertRaises(SystemExit):
            patch.apply(BASELINE.read_text().replace('"FOXGLOVE"', '"FOXGLOVE2"'))


class XboxDefault(Base):
    def test_boot_default_is_xbox_and_flysky_commands_are_dropped(self):
        self.joy(); self.release()
        self.m.on_command('FLYSKY', tw(0.1, 0.2)); self.now += 0.05; self.m.watchdog()
        self.assertFalse(self.m.channels['FLYSKY'].engaged)
        self.m.on_command('REMOTE', tw(0.2, 0.0)); self.now += 0.05; self.m.watchdog()
        self.assertEqual(self.m.active_name, 'REMOTE'); self.assertAlmostEqual(self.last_out().linear.x, 0.2)

    def test_policy_reports_controller(self):
        self.m.publish_mode()
        p = self.policy(); self.assertEqual(p['manual_controller'], 'XBOX'); self.assertTrue(p['flysky_drive_enabled'])


class Handover(Base):
    def test_refused_while_released(self):
        self.joy(); self.release()
        ok, why = self.m.select_controller('FLYSKY')
        self.assertFalse(ok); self.assertIn('Latch the E-STOP', why); self.assertEqual(self.m.manual_controller, 'XBOX')

    def test_allowed_while_latched_flushes_and_keeps_latch(self):
        self.joy(); self.release()
        self.m.on_command('REMOTE', tw(0.2)); self.now += 0.05; self.m.watchdog()
        self.latch()
        ok, why = self.m.select_controller('FLYSKY')
        self.assertTrue(ok, why); self.assertEqual(self.m.manual_controller, 'FLYSKY')
        self.assertTrue(self.m.remote_stop.latched)
        self.assertTrue(all(not c.engaged for c in self.m.channels.values()))
        self.assertEqual(self.last_out().linear.x, 0.0)

    def test_unknown_target_refused(self):
        self.assertFalse(self.m.select_controller('PS5')[0])

    def test_service_wrapper(self):
        r = self.m.select_controller_service('FLYSKY', NS(success=None, message=None))
        self.assertTrue(r.success)                     # startup latch is a latch


class FlyskySelected(Base):
    def setUp(self):
        super().setUp()
        self.joy(); self.assertTrue(self.m.select_controller('FLYSKY')[0]); self.release()

    def test_flysky_drives_and_xbox_drive_is_dropped(self):
        self.m.on_command('REMOTE', tw(0.2)); self.now += 0.05; self.m.watchdog()
        self.assertFalse(self.m.channels['REMOTE'].engaged)
        self.m.on_command('FLYSKY', tw(0.1, -0.3)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.assertEqual(self.m.active_name, 'FLYSKY')
        self.assertAlmostEqual(self.last_out().linear.x, 0.1); self.assertAlmostEqual(self.last_out().angular.z, -0.3)

    def test_mux_clamps_independently(self):
        self.m.on_command('FLYSKY', tw(5.0, -9.0)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.assertAlmostEqual(self.last_out().linear.x, 0.15); self.assertAlmostEqual(self.last_out().angular.z, -0.60)

    def test_stale_flysky_stops_in_one_cycle(self):
        self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.now += 0.40; self.joy(); self.m.watchdog()
        self.assertEqual(self.last_out().linear.x, 0.0); self.assertIsNone(self.m.active_name)

    def test_flysky_stop_latches_and_xbox_b_still_stops(self):
        self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.m.on_flysky_stop(None)
        self.assertTrue(self.m.remote_stop.latched); self.assertEqual(self.m.remote_stop.reason, 'REMOTE STOP: FlySky stop')
        self.assertEqual(self.last_out().linear.x, 0.0)
        self.release(); self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.latch(); self.assertEqual(self.last_out().linear.x, 0.0)

    def test_xbox_absence_still_latches(self):
        self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.now += 0.6; self.m.watchdog()                # no /joy for 0.6 s
        self.assertTrue(self.m.remote_stop.latched)
        self.assertIn('joystick unavailable', self.m.remote_stop.reason)
        self.assertEqual(self.last_out().linear.x, 0.0)

    def test_back_to_xbox_needs_latch_and_then_drops_flysky(self):
        self.assertFalse(self.m.select_controller('XBOX')[0])
        self.latch(); self.assertTrue(self.m.select_controller('XBOX')[0]); self.release()
        self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.assertFalse(self.m.channels['FLYSKY'].engaged)


class GateOff(Base):
    enabled = False

    def test_cannot_select_flysky_and_its_commands_are_dropped(self):
        self.joy()
        ok, why = self.m.select_controller('FLYSKY')
        self.assertFalse(ok); self.assertIn('disabled', why)
        self.m.manual_controller = 'FLYSKY'                # even if forced, the gate still drops commands
        self.release(); self.m.on_command('FLYSKY', tw(0.1)); self.now += 0.05; self.joy(); self.m.watchdog()
        self.assertFalse(self.m.channels['FLYSKY'].engaged)


if __name__ == '__main__':
    unittest.main()
