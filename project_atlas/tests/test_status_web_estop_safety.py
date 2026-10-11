"""E-STOP latch, drive refusal, stop-during-shutdown and reboot removal in rover-status-web.

Imports the real atlas_status_web module with ROS packages stubbed (no rclpy needed), replaces
its ROS bridge with a recorder, and drives the real HTTP handler's do_POST. No network, no ROS.
"""
import email.message
import io
import json
import sys
import time
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


def _stub_ros():
    class Msg:
        def __init__(self, *a, **k): pass
    def module(name, **attrs):
        m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
    if 'rclpy' in sys.modules and not getattr(sys.modules['rclpy'], '_atlas_stub', False):
        return
    def no_ros(*a, **k): raise RuntimeError('ROS unavailable in unit test')
    module('rclpy', init=no_ros, create_node=no_ros, spin=no_ros, ok=lambda: False, shutdown=lambda: None, _atlas_stub=True)
    module('rclpy.executors', SingleThreadedExecutor=Msg)
    module('rclpy.qos', DurabilityPolicy=Msg, QoSProfile=Msg, ReliabilityPolicy=Msg, qos_profile_sensor_data=None)
    module('geometry_msgs'); module('geometry_msgs.msg', PoseWithCovarianceStamped=Msg, Twist=Msg, PoseStamped=Msg)
    module('nav_msgs'); module('nav_msgs.msg', OccupancyGrid=Msg, Odometry=Msg, Path=Msg)
    module('sensor_msgs'); module('sensor_msgs.msg', NavSatFix=Msg, LaserScan=Msg, CompressedImage=Msg, Joy=Msg)
    module('std_msgs'); module('std_msgs.msg', Bool=Msg, Float32=Msg, String=Msg, Int32=Msg, Empty=Msg)
    module('tf2_ros', Buffer=Msg, TransformListener=Msg)


_stub_ros()
import atlas_status_web as web  # noqa: E402


class Recorder:
    """Stands in for AtlasRosNode: records what would be published."""
    def __init__(self, ready=True, latch_pub=True, policy=None):
        import threading
        self.ready, self.lock, self.data, self.events = ready, threading.Lock(), {}, []
        self.commissioning_stop_pub = types.SimpleNamespace(publish=lambda m: self.events.append('LATCH')) if latch_pub else None
        self.web_estop_at = float('-inf')
        if policy is not None:
            self.data['control_policy'] = {'value': json.dumps(policy), 'ts': time.time()}
    def publish(self, linear=0.0, angular=0.0):
        if not self.ready: return False
        self.events.append(('TWIST', float(linear), float(angular))); return True
    latch_drive_stop = web.AtlasRosNode.latch_drive_stop
    drive_stop_latched = web.AtlasRosNode.drive_stop_latched


def post(form, headers=None):
    body = '&'.join(f'{k}={v}' for k, v in form.items()).encode()
    h = web.Handler.__new__(web.Handler)
    msg = email.message.Message()
    msg['Content-Type'] = 'application/x-www-form-urlencoded'; msg['Content-Length'] = str(len(body))
    for k, v in (headers or {}).items(): msg[k] = v
    h.headers, h.rfile, h.wfile = msg, io.BytesIO(body), io.BytesIO()
    h.path, h.command, h.request_version, h.requestline = '/', 'POST', 'HTTP/1.1', 'POST / HTTP/1.1'
    h.client_address, h.close_connection = ('127.0.0.1', 5555), True
    h.do_POST()
    raw = h.wfile.getvalue().decode()
    status = int(raw.split(' ', 2)[1]); payload = json.loads(raw.split('\r\n\r\n', 1)[1])
    return status, payload


class EStopSafety(unittest.TestCase):
    def setUp(self):
        self._ros = web.ROS
        web.SHUTDOWN_PENDING.clear()

    def tearDown(self):
        web.ROS = self._ros
        web.SHUTDOWN_PENDING.clear()

    def use(self, **kw):
        web.ROS = Recorder(**kw); return web.ROS

    def test_e_stop_sends_zero_then_latches(self):
        r = self.use()
        status, p = post({'action': 'e_stop'})
        self.assertEqual(status, 200); self.assertTrue(p['latched'])
        self.assertEqual(r.events, [('TWIST', 0.0, 0.0), 'LATCH'])
        self.assertIn('remote', p['message'].lower())

    def test_drive_after_e_stop_is_refused_and_zeroed(self):
        r = self.use()
        post({'action': 'e_stop'}); r.events.clear()
        status, p = post({'action': 'drive', 'linear': '.65', 'angular': '0'})
        self.assertEqual(status, 409); self.assertFalse(p['ok'])
        self.assertEqual(r.events, [('TWIST', 0.0, 0.0)])  # never a non-zero command

    def test_drive_refused_while_mux_reports_latch(self):
        r = self.use(policy={'stop_latched': True, 'stop_reason': 'REMOTE STOP: B pressed'})
        status, _ = post({'action': 'drive', 'linear': '.65', 'angular': '0'})
        self.assertEqual(status, 409)
        self.assertNotIn(('TWIST', 0.65, 0.0), r.events)

    def test_drive_allowed_when_unlatched_or_policy_stale(self):
        r = self.use(policy={'stop_latched': False})
        status, _ = post({'action': 'drive', 'linear': '.65', 'angular': '0'})
        self.assertEqual(status, 200); self.assertIn(('TWIST', 0.65, 0.0), r.events)
        # A stale policy does not block (the mux itself remains the authority) ...
        r2 = self.use(); r2.data['control_policy'] = {'value': json.dumps({'stop_latched': True}), 'ts': time.time() - 5}
        self.assertEqual(post({'action': 'drive', 'linear': '.65', 'angular': '0'})[0], 200)

    def test_latch_released_only_by_mux_policy_never_by_web(self):
        r = self.use()
        post({'action': 'e_stop'})
        # No web action publishes a release; even 'stop' only sends zero.
        for action in ('stop', 'reset', 'release', 'remote_stop_reset'):
            post({'action': action})
        self.assertNotIn('RELEASE', r.events)
        self.assertEqual([e for e in r.events if e != 'LATCH' and e != ('TWIST', 0.0, 0.0)], [])
        # After the grace period, the latch state follows the mux policy only.
        r.web_estop_at = time.monotonic() - 5
        r.data['control_policy'] = {'value': json.dumps({'stop_latched': False}), 'ts': time.time()}
        self.assertEqual(post({'action': 'drive', 'linear': '.3', 'angular': '0'})[0], 200)

    def test_e_stop_without_latch_publisher_reports_failure_but_still_zeroes(self):
        r = self.use(latch_pub=False)
        status, p = post({'action': 'e_stop'})
        self.assertEqual(status, 503); self.assertFalse(p['latched'])
        self.assertEqual(r.events, [('TWIST', 0.0, 0.0)])
        self.assertIn('remote stop', p['message'].lower())

    def test_e_stop_when_ros_not_ready_says_zero_not_sent(self):
        r = self.use(ready=False)
        status, p = post({'action': 'e_stop'})
        self.assertEqual(status, 503); self.assertFalse(p['latched'])
        self.assertIn('NOT sent', p['message']); self.assertIn('remote stop', p['message'].lower())
        self.assertEqual(r.events, [])

    def test_stop_and_e_stop_accepted_while_shutdown_pending(self):
        r = self.use()
        web.SHUTDOWN_PENDING.set()
        self.assertEqual(post({'action': 'stop'})[0], 200)
        self.assertEqual(post({'action': 'e_stop'})[0], 200)
        self.assertIn('LATCH', r.events)
        # ... but everything else stays blocked.
        self.assertEqual(post({'action': 'drive', 'linear': '.65', 'angular': '0'})[0], 409)
        self.assertEqual(post({'action': 'camera', 'axis': 'pan', 'direction': '1'})[0], 409)

    def test_shutdown_latches_before_poweroff(self):
        src = (SCRIPTS / 'atlas_status_web.py').read_text(encoding='utf-8')
        block = src[src.index('elif action == "shutdown":'):]
        block = block[:block.index('def power_off')]
        self.assertLess(block.index('SHUTDOWN_PENDING.set()'), block.index('stop_rover()'))
        self.assertLess(block.index('stop_rover()'), block.index('ROS.latch_drive_stop()'))


if __name__ == '__main__':
    unittest.main()


class MuxHonoursWebEStop(unittest.TestCase):
    """The web E-STOP publishes /atlas/voice/stop; prove the mux then drops WEB drive and keeps
    the remote as the only release path (real RemoteStop + real mux methods, no ROS)."""

    def setUp(self):
        import ast
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from atlas_remote_stop import RemoteStop
        src = (SCRIPTS / 'atlas_cmd_vel_mux.py').read_text(encoding='utf-8'); tree = ast.parse(src)
        consts = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  for t in n.targets if isinstance(t, ast.Name) and t.id.startswith('REMOTE_STOP_')}
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AtlasCmdVelMux')
        cls.bases, cls.decorator_list = [], []
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                    and n.name in {'moving', 'copy_twist', 'hold_remote_stop', 'on_voice_stop', 'on_stop_joy'}]
        self.now = 100.0
        tw = lambda x=0.0, z=0.0: NS(linear=NS(x=x, y=0.0, z=0.0), angular=NS(x=0.0, y=0.0, z=z))
        scope = dict(time=NS(monotonic=lambda: self.now), Twist=tw, String=lambda data='': NS(data=data), **consts)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'mux', 'exec'), scope)
        m = scope['AtlasCmdVelMux']()
        m.remote_stop = RemoteStop(); m.remote_stop.latched = False; m.remote_stop.last_rx = self.now
        m.channels = {'REMOTE': NS(engaged=False, command=tw()), 'WEB': NS(engaged=True, command=tw(0.65))}
        m.commission_until, m._remote_held_yaw, m.active_name, m.last_sent = 0.0, 0.0, 'WEB', tw(0.65)
        m.output, m.safety_output, m.publish_mode = Mock(), Mock(), Mock()
        m._remote_stop_hold_latched = m._remote_stop_hold_reason = None
        m._remote_stop_last_zero = m._remote_stop_last_status = float('-inf')
        self.m, self.tw = m, tw

    def test_voice_stop_latches_flushes_web_and_publishes_zero(self):
        self.m.on_voice_stop(None)
        self.assertTrue(self.m.remote_stop.latched)
        self.assertFalse(self.m.channels['WEB'].engaged)
        self.assertFalse(self.m.moving(self.m.output.publish.call_args.args[0]))
        self.assertIsNone(self.m.active_name)

    def test_only_physical_remote_neutral_lb_hold_releases(self):
        self.m.on_voice_stop(None)
        axes, idle = [0.0] * 6, [0] * 11
        lb = list(idle); lb[4] = 1
        self.m.remote_stop.last_rx = self.now
        joy = lambda b: types.SimpleNamespace(axes=axes, buttons=b)
        def feed(buttons, seconds):              # joystick packets at 20 Hz, as on the rover
            for _ in range(int(seconds / 0.05)):
                self.now += 0.05; self.m.on_stop_joy(joy(buttons))
        feed(idle, 0.5)                          # sticks neutral, no buttons: arms the reset
        feed(lb, 1.5); self.assertTrue(self.m.remote_stop.latched)   # LB held 1.5 s: still latched
        feed(lb, 0.7); self.assertTrue(self.m.remote_stop.latched)   # held past 2 s: still latched until LB released
        feed(idle, 0.1)                          # let go of LB
        self.assertFalse(self.m.remote_stop.latched)
