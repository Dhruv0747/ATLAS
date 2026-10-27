#!/usr/bin/env python3
"""SIMULATION ONLY. Runs the REAL atlas_sensor_recovery.py (original or patched) under a stub rclpy.

Every monitor is fed from simulated sources; the recovery's own timers run at their real periods, and its
`systemctl --user restart` calls hit the container's real systemd user manager. The base-owned monitors are fed
from the fake base heartbeat, lidar from the fake lidar heartbeat; /cmd_vel and /atlas/control_policy from
world.json (so tests can break the stop guard). Log lines are prefixed with $INVOCATION_ID (sim "journal").
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import types

SIM = Path(os.environ['SIM_STATE'])
SCRIPTS = Path(os.environ['SIM_SCRIPTS'])
INV = os.environ.get('INVOCATION_ID', '-')
OUT_LOCK = threading.Lock()


def emit(msg):
    with OUT_LOCK:
        print(f'{INV} {time.time():.3f} {msg}', flush=True)


# ---------------- stub ROS ----------------
class _Logger:
    def info(self, m, **_):
        emit(f'[INFO] [atlas_sensor_recovery]: {m}')

    warning = warn = info

    def error(self, m, **_):
        emit(f'[ERROR] [atlas_sensor_recovery]: {m}')


class Node:
    def __init__(self, name):
        self._subs, self._timers = {}, []

    def create_publisher(self, typ, topic, qos):
        return types.SimpleNamespace(publish=lambda msg: None)

    def create_subscription(self, typ, topic, cb, qos, raw=False):
        self._subs[topic] = cb

    def create_timer(self, period, cb):
        self._timers.append([period, time.monotonic() + period, cb])

    def get_logger(self):
        return _Logger()

    def destroy_node(self):
        pass


class Msg:
    def __init__(self, data=None, **kw):
        self.data = data
        self.status, self.latitude, self.longitude = types.SimpleNamespace(status=0), 0.0, 0.0
        self.__dict__.update(kw)


def _cls(name):
    return type(name, (Msg,), {})


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class Twist:
    def __init__(self, lin=0.0, ang=0.0):
        self.linear, self.angular = _Vec(lin), _Vec(0.0, 0.0, ang)


class String(Msg):
    pass


for n in ('rclpy', 'rclpy.node', 'rclpy.executors', 'rclpy.qos', 'geometry_msgs', 'geometry_msgs.msg', 'nav_msgs',
          'nav_msgs.msg', 'sensor_msgs', 'sensor_msgs.msg', 'std_msgs', 'std_msgs.msg'):
    _mod(n)
sys.modules['rclpy'].__dict__.update(init=lambda: None, ok=lambda: False, shutdown=lambda: None)
sys.modules['rclpy.node'].Node = Node
sys.modules['rclpy.executors'].ExternalShutdownException = type('ExternalShutdownException', (Exception,), {})
sys.modules['rclpy.qos'].__dict__.update(QoSProfile=lambda **k: None, DurabilityPolicy=types.SimpleNamespace(TRANSIENT_LOCAL=1),
                                        ReliabilityPolicy=types.SimpleNamespace(RELIABLE=1))
sys.modules['geometry_msgs.msg'].Twist = Twist
sys.modules['nav_msgs.msg'].__dict__.update(OccupancyGrid=_cls('OccupancyGrid'), Odometry=_cls('Odometry'))
sys.modules['sensor_msgs.msg'].__dict__.update(CompressedImage=_cls('CompressedImage'), Imu=_cls('Imu'),
                                              LaserScan=_cls('LaserScan'), NavSatFix=_cls('NavSatFix'))
sys.modules['std_msgs.msg'].__dict__.update(Float32=_cls('Float32'), Int32=_cls('Int32'), String=String)

# ---------------- load the real recovery ----------------
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('atlas_sensor_recovery', SCRIPTS / 'atlas_sensor_recovery.py')
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)
rec.STARTUP_GRACE = float(os.environ.get('SIM_GRACE', rec.STARTUP_GRACE))   # timing only; logic untouched
node = rec.AtlasRecovery()

BASE_FED = {'imu', 'wheel_odometry', 'encoder_fl', 'encoder_health'}


def hb_fresh(name, max_age=0.3):
    try:
        d = json.loads((SIM / name).read_text())
        return time.time() - d['wall'] <= max_age
    except (OSError, ValueError, KeyError):
        return False


def world():
    try:
        return json.loads((SIM / 'world.json').read_text())
    except (OSError, ValueError):
        return {}


last_feed = 0.0
while True:
    now = time.monotonic()
    if now - last_feed >= 0.1:
        last_feed = now
        w = world()
        node.on_velocity(Twist(w.get('cmd_lin', 0.0), w.get('cmd_ang', 0.0)))
        node.on_control_policy(String(json.dumps({'stop_latched': w.get('stop_latched', True), 'manual_only': True})))
        base_ok, lidar_ok = hb_fresh('hb'), hb_fresh('lidar_hb')
        for item in rec.MONITORS:
            if item.name in BASE_FED:
                if not base_ok:
                    continue
                if item.name == 'encoder_health':
                    st = w.get('recovery_encoder_state') or w.get('encoder_state', 'READY')
                    node.on_message(item.name, String(json.dumps({'state': st})))
                else:
                    node.on_message(item.name, item.msg_type())
            elif item.name == 'lidar':
                if lidar_ok:
                    node.on_message(item.name, item.msg_type())
            elif item.name == 'bms':
                node.on_message(item.name, String(json.dumps({'ok': True})))
            elif item.msg_type is String:
                node.on_message(item.name, String('ok'))
            else:
                node.on_message(item.name, item.msg_type())
    for t in node._timers:
        if now >= t[1]:
            t[1] = now + t[0]
            t[2]()
    time.sleep(0.02)
