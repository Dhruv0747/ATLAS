#!/usr/bin/env python3
"""Isolated benchmark: rover-status-web subscription/executor cost, current layout vs proposed layouts.

Runs entirely on a PRIVATE DDS domain (ROS_DOMAIN_ID=77, ROS_LOCALHOST_ONLY=1), so it never
sees or touches the live ATLAS graph: synthetic publishers replay the topic list parsed from
atlas_status_web.py at the rates measured live on 2026-10-11 (status API observed_hz plus
`ros2 topic hz`). Only the subscriber process's CPU is measured.

  bench_status_executor.py pub                 # synthetic publishers (run first, separate process)
  bench_status_executor.py sub <variant> <s>   # variants: current | split | split_raw
Variants:
  current   one node, every subscription + TF listener + 3 timers, rclpy.spin()  (as deployed)
  split     same subscriptions and callbacks, but topics >=5 Hz (and TF) on a "hot" node and the rest
            on a "cold" node, each with its own SingleThreadedExecutor thread
  split_raw split, plus hot String/Float32/Int32 topics subscribed raw (bytes) and deserialized only
            when the HTTP layer reads them (lazy decode; same values served)
"""
import ast, os, re, sys, threading, time
from collections import deque
from pathlib import Path

os.environ.setdefault('ROS_DOMAIN_ID', '77'); os.environ.setdefault('ROS_LOCALHOST_ONLY', '1')
assert os.environ['ROS_DOMAIN_ID'] != '0', 'refusing to run on the live ATLAS domain'
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from rclpy.serialization import deserialize_message
from std_msgs.msg import String, Float32, Int32, Bool
from sensor_msgs.msg import LaserScan, Joy, NavSatFix
from nav_msgs.msg import Odometry, Path as NavPath
from geometry_msgs.msg import Twist, PoseWithCovarianceStamped, PoseStamped, TransformStamped
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformListener

TYPES = {'String': String, 'Float32': Float32, 'Int32': Int32, 'Bool': Bool, 'LaserScan': LaserScan, 'Joy': Joy,
         'NavSatFix': NavSatFix, 'Odometry': Odometry, 'NavPath': NavPath, 'Twist': Twist,
         'PoseWithCovarianceStamped': PoseWithCovarianceStamped, 'PoseStamped': PoseStamped}
SRC = Path(__file__).resolve().parents[2] / 'scripts' / 'atlas_status_web.py'
# Live rates, Jetson 2026-10-11 08:5x IST (rover parked; no dashboard client)
RATES = {'/radar/hub/status': 20.6, '/radar/targets': 19.9, '/joy': 19.4, '/atlas/drive_pid/diagnostics': 10, '/steering/front_angle_deg': 10,
         '/steering/rear_angle_deg': 10, '/steering/mode': 10, '/atlas/steering_calibration/status': 10, '/yahboom/imu/roll': 10,
         '/yahboom/imu/pitch': 10, '/yahboom/imu/heading': 10, '/yahboom/encoder/m1': 10, '/yahboom/encoder/m2': 10, '/yahboom/encoder/m3': 10,
         '/yahboom/encoder/m4': 10, '/atlas/encoder_health': 10, '/atlas/control_policy': 10, '/odom': 10, '/im10a/dashboard_json': 10,
         '/ultrasonic/status': 7.9, '/scan': 7.6, '/cmd_vel': 4.7, '/arduino/pca9685/status': 3.6, '/camera/arducam/status': 3.6,
         '/ultrasonic/validity': 3.6, '/camera/detections/json': 3.3, '/atlas/agent/status': 2, '/atlas/agent/decision': 2, '/atlas/agent/state': 2,
         '/motor_speed': 1.8, '/amcl_pose': 1, '/radar/decoder_status': 1, '/thermal/amg8833/status': 1, '/thermal/amg8833/json': 1,
         '/battery/voltage': 1, '/battery/current': 1, '/battery/percent': 1, '/jetson/power/input_voltage': 1, '/jetson/power/input_current': 1,
         '/jetson/power/input_power': 1, '/jetson/power/cpu_gpu_power': 1, '/jetson/power/soc_power': 1, '/jetson/power/status': 1,
         '/gps/satellites': 1, '/gps/hdop': 1, '/gps/constellations': 1, '/gps/receiver_status': 1, '/gps/diagnostics': 1,
         '/atlas/mission_status': 1, '/gps/fix': 1}
for t in ('outside_temperature_c', 'outside_humidity_pct', 'pressure_hpa', 'gas_resistance_ohm', 'bme680/json', 'outside_status'):
    RATES['/environment/' + t] = 0.5
RATES['/atlas/agent_team/status'] = 0.5
for t in ('status', 'json', 'voltage', 'current', 'percent', 'power', 'cell1_voltage', 'cell2_voltage', 'cell3_voltage', 'cell4_voltage'):
    RATES['/bms/' + t] = 0.21
TF_HZ = 10.0  # /tf measured 5.7 Hz by the CLI under load (CLI under-reads ~25%); 10 Hz used, 2 transforms per message
HOT_HZ = 5.0
EXCLUDED = {'/camera/image_raw/compressed', '/camera/detections/compressed', '/map'}  # on-demand / latched in the real server


def topic_list():
    s = SRC.read_text(encoding='utf-8'); out = []; i = 0
    while (i := s.find('create_subscription(', i)) >= 0:
        j = i + len('create_subscription('); d, k = 1, j
        while d: d += {'(': 1, ')': -1}.get(s[k], 0); k += 1
        m = re.match(r"\s*(\w+)\s*,\s*['\"]([^'\"]+)['\"]", s[j:k - 1]); i = k
        if m and m.group(2) not in EXCLUDED: out.append((m.group(2), m.group(1)))
    return out


def sample(t, typ):
    m = TYPES[typ]()
    if typ == 'String': m.data = ('{"k":%d,' % len(t)) + '"v":"' + 'x' * (400 if 'json' in t or 'policy' in t or 'pid' in t else 120) + '"}'
    elif typ in ('Float32',): m.data = 1.5
    elif typ == 'Int32': m.data = 1234
    elif typ == 'Bool': m.data = True
    elif typ == 'LaserScan': m.ranges = [1.0] * 362; m.range_min, m.range_max = 0.15, 12.0; m.header.frame_id = 'laser'
    elif typ == 'Joy': m.axes = [0.0] * 8; m.buttons = [0] * 11
    return m


def pub():
    rclpy.init(); n = rclpy.create_node('bench_pub'); ex = SingleThreadedExecutor(); ex.add_node(n)
    for t, typ in topic_list():
        hz = RATES.get(t, 0.0)
        if hz <= 0: continue
        p = n.create_publisher(TYPES[typ], t, qos_profile_sensor_data if t == '/scan' else 10); msg = sample(t, typ)
        n.create_timer(1.0 / hz, lambda p=p, m=msg: p.publish(m))
    tfp = n.create_publisher(TFMessage, '/tf', 100)
    def tf():
        a = TransformStamped(); a.header.frame_id, a.child_frame_id = 'odom', 'base_link'; a.header.stamp = n.get_clock().now().to_msg(); a.transform.rotation.w = 1.0
        b = TransformStamped(); b.header.frame_id, b.child_frame_id = 'map', 'odom'; b.header.stamp = a.header.stamp; b.transform.rotation.w = 1.0
        tfp.publish(TFMessage(transforms=[a, b]))
    n.create_timer(1.0 / TF_HZ, tf)
    print('publishing', len(topic_list()), 'topics', flush=True); ex.spin()


class Store:
    def __init__(self): self.lock = threading.Lock(); self.data = {}; self.times = {}; self.n = 0
    def set(self, key, value):
        with self.lock:
            self.data[key] = {'value': value, 'ts': time.time()}
            self.times.setdefault(key, deque(maxlen=128)).append(time.monotonic()); self.n += 1


def sub(variant, seconds):
    rclpy.init(); st = Store(); topics = topic_list()
    cb = lambda key: (lambda m: st.set(key, getattr(m, 'data', m)))
    raw_cb = lambda key, typ: (lambda b: st.set(key, ('raw', typ, b)))  # decoded lazily by the HTTP reader
    hot = rclpy.create_node('bench_hot'); cold = hot if variant == 'current' else rclpy.create_node('bench_cold')
    for t, typ in topics:
        node = hot if RATES.get(t, 0) >= HOT_HZ else cold
        qos = qos_profile_sensor_data if t == '/scan' else 10
        if variant == 'split_raw' and node is hot and typ in ('String', 'Float32', 'Int32'):
            node.create_subscription(TYPES[typ], t, raw_cb(t, typ), qos, raw=True)
        else:
            node.create_subscription(TYPES[typ], t, cb(t), qos)
    buf = Buffer(); TransformListener(buf, hot)
    hot.create_timer(0.1, lambda: None); cold.create_timer(0.5, lambda: None); hot.create_timer(0.10, lambda: None)  # watchdog, map pose, camera tick
    execs = [SingleThreadedExecutor()]; execs[0].add_node(hot)
    if cold is not hot: execs.append(SingleThreadedExecutor()); execs[1].add_node(cold)
    for e in execs: threading.Thread(target=e.spin, daemon=True).start()
    time.sleep(5)  # discovery / warm-up
    hz = os.sysconf('SC_CLK_TCK'); f = lambda: sum(map(int, open('/proc/self/stat').read().split()[13:15]))
    c0, n0, t0 = f(), st.n, time.monotonic(); time.sleep(seconds); c1, n1, t1 = f(), st.n, time.monotonic()
    dt = t1 - t0
    print(f'RESULT variant={variant} subs={len(topics)} cpu_pct_one_core={100 * (c1 - c0) / hz / dt:.1f} '
          f'msgs_per_s={(n1 - n0) / dt:.1f} us_per_msg={1e6 * (c1 - c0) / hz / max(1, n1 - n0):.0f}', flush=True)
    os._exit(0)


if __name__ == '__main__':
    pub() if sys.argv[1] == 'pub' else sub(sys.argv[2], float(sys.argv[3]))
